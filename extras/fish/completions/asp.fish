set profiles (grep '^\[profile' $AWS_HOME/config | grep -v '\-sso\]' | sed -e 's/^\[profile \([a-zA-Z0-9_-]*\).*/\1/' | sort)

complete -f -c asp -a "$profiles"
