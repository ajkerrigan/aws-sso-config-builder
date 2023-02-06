import json
import logging
import re
import sys
import textwrap
import time
import webbrowser
from collections import ChainMap
from concurrent.futures import ThreadPoolExecutor, as_completed
from operator import itemgetter

import boto3
import click
import keyring
from botocore.config import Config
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.table import Column

DEFAULT_PROFILE_TEMPLATE = """
    [profile {profile_name}]
    sso_session = {sso_session}
    sso_account_id = {account_id}
    sso_role_name = {role_name}
"""

SSO_SESSION_BLOCK = """
    [sso-session {sso_session_name}]
    sso_start_url = {sso_start_url}
    sso_region = us-east-1
"""


def register_id_client(oidc_client):
    log = logging.getLogger("register_id_client")
    keyring_service, keyring_username = "aws-sso-oidc", "sso-config-generator"
    id_client = keyring.get_password(keyring_service, keyring_username)
    if not id_client:
        log.info("No cached ID client found, registering a new one...")
        id_client = {
            k: v
            for k, v in oidc_client.register_client(
                clientName=keyring_username, clientType="public"
            ).items()
            if k in {"clientId", "clientSecret"}
        }
        keyring.set_password(keyring_service, keyring_username, json.dumps(id_client))
    else:
        log.info("Using cached ID client...")
        id_client = json.loads(id_client)
    return id_client


def create_access_token(oidc_client, id_client, sso_start_url):
    device_auth = oidc_client.start_device_authorization(
        **id_client, startUrl=sso_start_url
    )
    webbrowser.open_new_tab(device_auth["verificationUriComplete"])

    with progress:
        auth_task = progress.add_task(
            f"Waiting for device authorization...", total=None
        )
        while not progress.finished:
            try:
                access_token = oidc_client.create_token(
                    **id_client,
                    grantType="urn:ietf:params:oauth:grant-type:device_code",
                    deviceCode=device_auth["deviceCode"],
                )["accessToken"]
                progress.update(auth_task, total=100, completed=100)
            except oidc_client.exceptions.AuthorizationPendingException:
                time.sleep(5)

    return access_token


def list_accounts(sso_client, access_token):
    with progress:
        list_accounts_task = progress.add_task("Listing accounts...", total=None)

        paginator = sso_client.get_paginator("list_accounts")
        accounts = [
            acc
            for page in paginator.paginate(accessToken=access_token)
            for acc in page["accountList"]
        ]
        progress.update(list_accounts_task, total=100, completed=100)
    return accounts


def get_roles(account, sso_client, access_token):
    paginator = sso_client.get_paginator("list_account_roles")
    return {
        account["accountName"]: [
            role
            for page in paginator.paginate(
                accessToken=access_token, accountId=account["accountId"]
            )
            for role in page["roleList"]
        ]
    }


def list_account_roles(sso_client, access_token, accounts):
    account_roles = {}
    with progress:
        task = progress.add_task("Listing roles for accounts...", total=len(accounts))
        with ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(get_roles, account, sso_client, access_token)
                for account in accounts
            ]

            for future in as_completed(futures):
                account_roles.update(future.result())
                progress.advance(task)
    return account_roles


def munge_profile_name(account_name, role_name, regex_replacements):
    replacements = ChainMap(
        regex_replacements,
        {
            "_": "-",
            " ": "-",
        },
    )

    profile_name = "-".join((account_name, role_name))
    for old, new in replacements.items():
        profile_name = re.sub(old, new, profile_name)

    return profile_name


def build_config_profiles(account_roles, regex_replacements):
    profiles = [
        {
            "name": munge_profile_name(
                account_name, role["roleName"], regex_replacements
            ),
            "account_name": account_name,
            "role_name": role["roleName"],
            "account_id": role["accountId"],
        }
        for account_name in sorted(account_roles)
        for role in sorted(account_roles[account_name], key=itemgetter("roleName"))
    ]
    return profiles


def format_profile(template, profile, sso_session_name, **extra_vars):
    return textwrap.dedent(
        template.format(
            profile_name=profile["name"],
            account_name=profile["account_name"],
            account_id=profile["account_id"],
            role_name=profile["role_name"],
            sso_session=sso_session_name,
            **extra_vars,
        )
    )


def generate_config_blocks(
    sso_directories,
    profile_template=DEFAULT_PROFILE_TEMPLATE,
    regex_replacements={},
    **extra_vars,
):
    sess = boto3.Session(region_name="us-east-1")
    oidc_client = sess.client("sso-oidc")
    sso_client = sess.client(
        "sso", config=Config(retries={"mode": "standard", "max_attempts": 10})
    )
    id_client = register_id_client(oidc_client)
    config_blocks = []

    for sso_directory in sorted(sso_directories):
        sso_start_url = f"https://{sso_directory}.awsapps.com/start"
        access_token = create_access_token(oidc_client, id_client, sso_start_url)
        accounts = list_accounts(sso_client, access_token)
        account_roles = list_account_roles(sso_client, access_token, accounts)
        profiles = build_config_profiles(account_roles, regex_replacements)

        config_blocks.append(
            textwrap.dedent(
                SSO_SESSION_BLOCK.format(
                    sso_session_name=sso_directory, sso_start_url=sso_start_url
                )
            )
        )
        config_blocks.extend(
            [
                format_profile(
                    textwrap.dedent(profile_template),
                    profile,
                    sso_directory,
                    **extra_vars,
                )
                for profile in profiles
            ]
        )

    return "".join(config_blocks)


def validate_extras(ctx, param, value):
    split_values = [v.split("=") for v in value]
    if any(len(v) != 2 for v in split_values):
        raise click.BadParameter(
            "Extra vars must be key/value pairs in the form: key=value"
        )
    return dict(split_values)


def validate_replacements(ctx, param, value):
    split_values = [v.split(",") for v in value]
    if any(len(v) != 2 for v in split_values):
        raise click.BadParameter(
            "Replacements must be strings in the form: pattern,replacement"
        )
    return dict(split_values)


@click.command(
    context_settings=dict(help_option_names=["-h", "--help"]), no_args_is_help=True
)
@click.option(
    "--sso-directories",
    "-s",
    multiple=True,
    required=True,
    help="""
        SSO directory names, which will be used:

        \b
        - To define "sso-session" config blocks
        - To build an SSO start URL
    """,
)
@click.option(
    "--profile-template",
    "-t",
    default=DEFAULT_PROFILE_TEMPLATE,
    help="""
        An AWS CLI profile block template with {placeholders} for profile values

        \b
        Supported placeholder variables:
        - profile_name
        - account_name
        - account_id
        - role_name
        - sso_session

        ...and any other "key" provided in --extra-vars
    """,
)
@click.option(
    "--extra-vars",
    "-e",
    multiple=True,
    callback=validate_extras,
    help="""
        Custom variables in the form "key=value" that can be referenced with {placeholders}
        in a profile template.
    """,
)
@click.option(
    "--regex-replacements",
    "-r",
    multiple=True,
    callback=validate_replacements,
    help="Regex replacements to perform on generated profile names, in the form 'pattern,replacement'",
)
def cli(sso_directories, profile_template, regex_replacements, extra_vars):
    logging.basicConfig(level=logging.INFO)

    print(
        generate_config_blocks(
            sso_directories, profile_template, regex_replacements, **extra_vars
        )
    )


text_column = TextColumn("{task.description}", table_column=Column(width=40))
progress = Progress(
    text_column,
    BarColumn(),
    TaskProgressColumn(),
    console=Console(file=sys.stderr),
    expand=False,
)

if __name__ == "__main__":
    cli()
