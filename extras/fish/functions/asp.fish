function asp --description 'set the active AWS CLI profile'
    if test -n "$argv"
        set profile "$argv"
    else
        set profile (grep '^\[profile' $AWS_HOME/config | grep -v '\-sso\]' | sed -e 's/^\[profile \([a-zA-Z0-9_-]*\).*/\1/' | sort | fzf --tiebreak=begin)
    end

    set -gx AWS_PROFILE "$profile"
    set -gx AWS_DEFAULT_PROFILE "$profile"
end
