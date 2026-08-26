#!/bin/env bash

# For the `.desktop` file install command, where to?
dot_desktop_install_dir="${HOME}/.local/share/applications"
dot_desktop_install_name="ai-usage.desktop"
dot_desktop_autostart_dir="${HOME}/.config/autostart"

project_dir="${HOME}/git/luckydonald/ai-usage"
final_executable="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"


function do_run {
    echo "launching..."
    cd "${project_dir}"
    echo "building frontend..."
    (cd frontend && corepack yarn@4.9.2 build)
    echo "starting ai-usage..."
    ai-usage up
}

# ask user if they want to run/install/uninstall
while true; do
    # Determine if the script is not being run in a TTY (interactive)
    if [ ! -t 1 ]; then
        choice="run"
    elif [[ "$1" == ".desktop" ]]; then
        choice="run"
    else
        echo ""
        echo ""
        echo "Do you want to run the server now?"
        echo "Please enter 'run' for running the program."
        echo "Please enter 'install' or 'uninstall' for writing a run configuration to the system's autostart, or removing it."
        read -p "([run]/install/uninstall): " choice
        if [[ -z "$choice" ]]; then
            choice="run"
        fi
    fi
    case "$choice" in
        run)
            while true; do
                do_run
                sleep 1  # Wait for 1 seconds before trying again
            done
            ;;
        install)
            mkdir -p "${dot_desktop_install_dir}"
            dot_desktop_install_location="${dot_desktop_install_dir}/${dot_desktop_install_name}"
            dot_desktop_autostart_location="${dot_desktop_autostart_dir}/${dot_desktop_install_name}"
            dot_desktop_home_location="${HOME}/${dot_desktop_install_name}"
            echo '#!/usr/bin/env xdg-open' > ${dot_desktop_home_location}
            echo '[Desktop Entry]' >> ${dot_desktop_home_location}
            echo 'Version=1.0' >> ${dot_desktop_home_location}
            echo 'Type=Application' >> ${dot_desktop_home_location}
            echo 'Name=AI Usage' >> ${dot_desktop_home_location}
            echo 'Comment=Build the dashboard frontend and run ai-usage up' >> ${dot_desktop_home_location}
            echo "Path=${project_dir}" >> ${dot_desktop_home_location}
            echo "Exec=${final_executable} .desktop" >> ${dot_desktop_home_location}
            echo 'Icon=utilities-terminal' >> ${dot_desktop_home_location}
            echo 'Terminal=true' >> ${dot_desktop_home_location}
            echo 'Categories=Utility;Development;' >> ${dot_desktop_home_location}
            echo "File written to ${dot_desktop_home_location}."
            chmod +x ${dot_desktop_home_location}
            desktop-file-install --dir="${dot_desktop_install_dir}" "${dot_desktop_home_location}"
            echo "File installed to ${dot_desktop_install_location}."
            update-desktop-database "${dot_desktop_install_dir}"
            echo "Desktop Database updated."
            ln -s ${dot_desktop_install_location} "${dot_desktop_autostart_location}"

            chmod +x ${dot_desktop_autostart_location}
            echo "File symlinked to autostart at ${dot_desktop_autostart_dir}/${dot_desktop_install_name}"
            ;;
        uninstall)
            mkdir -p "${dot_desktop_install_dir}"
            dot_desktop_install_location="${dot_desktop_install_dir}/${dot_desktop_install_name}"
            dot_desktop_autostart_location="${dot_desktop_autostart_dir}/${dot_desktop_install_name}"
            rm -f "${dot_desktop_autostart_location}"
            echo "File symlink removed from autostart at ${dot_desktop_autostart_location}."
            rm -f "${dot_desktop_install_location}"
            echo "File removed from ${dot_desktop_install_location}."
            ;;
        *)
            echo "Invalid choice."
            ;;
    esac
done
