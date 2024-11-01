#!/bin/bash
#
# Install Microbio Automatic Photography Tool firmware

# exit script on first error
set -e

KLIPPER_SERIAL="/dev/ttyUSB0"

install_klipper(){(
	cd klipper

	# install klipper
	./scripts/install-debian.sh

	# build klipper-mcu
	echo "CONFIG_MACH_LINUX=y" > .config
	make olddefconfig
	make -j$(nproc)

	# install klipper-mcu
	sudo make flash
	sed -r 's/^ExecStart=.*$/\0\nExecStartPost=chown '"${USER}"' \/tmp\/klipper_host_mcu/' scripts/klipper-mcu.service | sudo tee /etc/systemd/system/klipper-mcu.service > /dev/null
	sudo systemctl daemon-reload
 	sudo systemctl enable --now klipper-mcu

	# install klipper to control board
	if [ -n "${KLIPPER_SERIAL}" ]; then
		echo "CONFIG_MACH_atmega1284p=y" > .config
		make olddefconfig
		make -j$(nproc)
		make flash FLASH_DEVICE="${KLIPPER_SERIAL}"
	fi
)}

install_mapt(){(
	# install the klipper config
	ln -s ${PWD}/klipper.cfg ${HOME}/printer.cfg

	# install the systemd service
	sudo tee /etc/systemd/system/mapt.service > /dev/null <<EOF
[Unit]
Requires=klipper.service
After=klipper.service

[Service]
ExecStart=${PWD}/backend.py
EOF
	sudo systemctl daemon-reload 
	#sudo systemctl enable --now mapt
)}

install_klipper
install_mapt

echo
echo Finished installing MAPT.
