# AWS SSO Config Builder <!-- omit in toc -->

[![PyPI - Version](https://img.shields.io/pypi/v/aws-sso-config-builder.svg)](https://pypi.org/project/aws-sso-config-builder)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/aws-sso-config-builder.svg)](https://pypi.org/project/aws-sso-config-builder)

-----

**Table of Contents**

- [The Gist](#the-gist)
- [Why](#why)
  - [...would someone use this?](#would-someone-use-this)
  - [...did I publish this?](#did-i-publish-this)
  - [...the focus on aws-vault?](#the-focus-on-aws-vault)
- [Installation](#installation)
  - [Into the Active Python Environment](#into-the-active-python-environment)
  - [With Pipx](#with-pipx)
  - [With Pipx Alongside Cog](#with-pipx-alongside-cog)
- [Usage](#usage)
  - [CLI](#cli)
    - [Quickstart with Defaults](#quickstart-with-defaults)
    - [More Options](#more-options)
  - [Python](#python)
    - [Quickstart with Defaults](#quickstart-with-defaults-1)
    - [Usage with Cog](#usage-with-cog)
- [Extras](#extras)
  - [Fish Convenience Functions](#fish-convenience-functions)
- [License](#license)

## The Gist

This tool generates AWS CLI configuration blocks for use with AWS IAM Identity Center
(formerly AWS SSO):

- [Named profiles](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-profiles.html)
- [SSO Session](https://docs.aws.amazon.com/cli/latest/userguide/sso-configure-profile-token.html#sso-configure-profile-token-auto-sso-session)

## Why

### ...would someone use this?

If they:

- Have access to a large or shifting set of accounts and roles through AWS SSO
- Don't already have tools in place to generate and maintain their named profiles
  - There are a few of these, I remember [aws-sso-util](https://github.com/benkehoe/aws-sso-util) in particular
- Want to automatically generate/regenerate templatized blocks without interfering with manually-defined sections

### ...did I publish this?

- After https://github.com/99designs/aws-vault/pull/1088 got merged, I wanted to update the script I use to update my AWS CLI config
- [Cog](https://nedbatchelder.com/code/cog/) wasn't on my radar when I started doing this stuff, but is just what I want to maintain the cleaner bits of my frankenconfig
- I wanted an excuse to try [Hatch](https://hatch.pypa.io/) on something

### ...the focus on aws-vault?

From the user experience perspective, the biggest win is that when using my aws-vault profiles, they just work:

- If I don't have an active SSO session, it pops open a browser to login without me having to manually type `aws sso login`
- If my session credentials are missing or expired, aws-vault refreshes them behind the scenes without killing running commands

But to be fair, a lot of wy I use aws-vault is habit. If you're not already using it, I'm not here to sell it to you.

## Installation

### Into the Active Python Environment

```console
pip install aws-sso-config-builder
```

### With Pipx

```console
pipx install aws-sso-config-builder
```

### With Pipx Alongside Cog

Useful to support [Usage with Cog](#usage-with-cog).

```console
pipx install cogapp
pipx inject cogapp aws-sso-config-builder
```

## Usage

Generate AWS CLI `sso-session` and `profile` blocks based on the accounts
and roles granted by your AWS SSO login(s).

Use as a CLI tool or from Python.

### CLI

#### Quickstart with Defaults

```console
generate-sso-profiles -s my-sso-directory-name
```

This will generate `sso-session` and `profile` blocks


#### More Options

<!---[[[cog
import click
import cog
from aws_sso_config_builder.gen_config import cli

ctx = click.Context(cli, info_name='generate-sso-profiles')
cog.outl(f'''
```console
{ctx.get_help()}
```
''')
]]]-->

```console
Usage: generate-sso-profiles [OPTIONS]

Options:
  -s, --sso-directories TEXT     SSO directory names, which will be used:

                                 - To define "sso-session" config blocks
                                 - To build an SSO start URL  [required]
  -t, --profile-template TEXT    An AWS CLI profile block template with
                                 {placeholders} for profile values

                                 Supported placeholder variables:
                                 - profile_name
                                 - account_name
                                 - account_id
                                 - role_name
                                 - sso_session

                                 ...and any other "key" provided in --extra-
                                 vars
  -e, --extra-vars TEXT          Custom variables in the form "key=value" that
                                 can be referenced with {placeholders} in a
                                 profile template.
  -r, --regex-replacements TEXT  Regex replacements to perform on generated
                                 profile names, in the form
                                 'pattern,replacement'
  --help                         Show this message and exit.
```

<!---[[[end]]]-->

### Python

#### Quickstart with Defaults

```python
from aws_sso_config_builder.gen_config import generate_config_blocks

print(generate_config_blocks(sso_directories=["my-sso-directory-name"]))
```

#### Usage with Cog

Use [Cog](https://nedbatchelder.com/code/cog/) to dynamically generate or replace specific sections inside an `~/.aws/config` file without touching manually-maintained blocks.

This invocation specifies:

- A custom profile template, including:
  - `credential_process` profiles for use with [aws-vault](https://github.com/99designs/aws-vault)
  - additional settings defined for each profile
- Some regex replacements to adjust the generated profile name

Add this Cog block to a new or existing `~/.aws/config` file:

```console
# [[[cog
# import cog
# from aws_sso_config_builder.gen_config import generate_config_blocks
#
# cog.outl(generate_config_blocks(
#     sso_directories=["home", "work"],
#     profile_template="""
#         [profile {profile_name}-sso]
#         sso_session = {sso_session}
#         sso_account_id = {account_id}
#         sso_role_name = {role_name}
#         output = json
#         region = us-east-2
#         cli_history = enabled
#
#         [profile {profile_name}]
#         credential_process = {aws_vault_path} exec --json {profile_name}-sso
#         output = json
#         region = us-east-2
#         cli_history = enabled
#     """,
#     regex_replacements={
#         "speckledmonkey": "sm",
#         "^Customer": "cust",
#         "Sandbox-": "sbx-"
#     },
#     aws_vault_path="/home/aj/go/bin/aws-vault",
# ))
# ]]]
# [[[end]]]
```

And then run:

```console
cog -r ~/.aws/config
```

Note that this depends on having Cog and aws-sso-config-builder installed in the same Python
environment. See also [Installation with Pipx Alongside Cog](#with-pipx-alongside-cog) above.

## Extras

### Fish Convenience Functions

These are probably specific to my environment, but sharing them because someone else might find them useful.

I use a fish convenience function ([asp](./extras/fish/functions/asp.fish)) to search or switch among AWS profiles. I'm reasonably sure that it was inspired at some point by a function of the same name in the [aws plugin for oh-my-zsh](https://github.com/ohmyzsh/ohmyzsh/blob/master/plugins/aws/aws.plugin.zsh).

Invoking `asp` with no arguments opens an [fzf](https://github.com/junegunn/fzf/) search of available profiles. But the command also supports tab completion with [this completion script](./extras/fish/completions/asp.fish).


## License

`aws-sso-config-builder` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
