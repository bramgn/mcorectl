# Bash completion for mcorectl
#
# Source this file or drop it in /etc/bash_completion.d/:
#   source /path/to/mcorectl_completion.bash
#
# To load automatically, add to ~/.bashrc:
#   source /path/to/mcorectl_completion.bash

_mcorectl() {
    local cur prev words cword
    _init_completion || return

    local commands="list advert contacts channels channel-send status telemetry route admin info stats set-txpower send recv listen rxlog neighbours trace"

    # Complete --port value with available serial devices
    if [[ "$prev" == "--port" ]]; then
        COMPREPLY=($(compgen -W "$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null)" -- "$cur"))
        return
    fi

    # Find the subcommand, skipping --port and its value
    local cmd="" cmd_idx=0
    local i
    for ((i = 1; i < cword; i++)); do
        local w="${words[$i]}"
        if [[ "$w" == "--port" ]]; then
            ((i++))
        elif [[ "$w" != -* ]]; then
            cmd="$w"
            cmd_idx=$i
            break
        fi
    done

    # No subcommand yet — complete command names or global flags
    if [[ -z "$cmd" ]]; then
        if [[ "$cur" == -* ]]; then
            COMPREPLY=($(compgen -W "--port --ble --help" -- "$cur"))
        else
            COMPREPLY=($(compgen -W "$commands" -- "$cur"))
        fi
        return
    fi

    # Count positional arguments after the subcommand (excluding flags and their values)
    local pos=0
    local skip_next=0
    for ((i = cmd_idx + 1; i < cword; i++)); do
        local w="${words[$i]}"
        if ((skip_next)); then
            skip_next=0
            continue
        fi
        if [[ "$w" == "--password" || "$w" == "--port" || "$w" == "--log" ]]; then
            skip_next=1
        elif [[ "$w" != -* ]]; then
            ((pos++))
        fi
    done

    case "$cmd" in
        advert)
            COMPREPLY=($(compgen -W "--flood --help" -- "$cur"))
            ;;

        admin)
            if [[ "$prev" == "--password" ]]; then
                COMPREPLY=()  # password value — no completion
            elif [[ "$cur" == -* ]]; then
                COMPREPLY=($(compgen -W "--password --help" -- "$cur"))
            elif ((pos == 0)); then
                COMPREPLY=()  # key_prefix — free text
            else
                # admin command (advert, reboot, set ...)
                COMPREPLY=($(compgen -W "advert reboot" -- "$cur"))
            fi
            ;;

        rxlog)
            if [[ "$prev" == "--log" ]]; then
                COMPREPLY=($(compgen -f -- "$cur"))
            else
                COMPREPLY=($(compgen -W "--log --help" -- "$cur"))
            fi
            ;;

        trace)
            COMPREPLY=($(compgen -W "-v --verbose --help" -- "$cur"))
            ;;

        status|telemetry|route|neighbours|send)
            COMPREPLY=($(compgen -W "--help" -- "$cur"))
            ;;

        contacts|channels|recv|listen|info|stats)
            COMPREPLY=($(compgen -W "--help" -- "$cur"))
            ;;
    esac
}

complete -F _mcorectl mcorectl
