#!/bin/bash
#
# Install Microbio Automatic Photography Tool firmware

# exit script on first error
set -e

KLIPPER_SERIAL=""

get_config(){
	# get USB device to install klipper to
	if lsusb | grep FT232 &>/dev/null; then
		RESP=""
		while ! [[ "${RESP}" =~ [ynYN] ]]; do
			read -p "Motor control board detected, do you want to install klipper firmware to it? This must be done once. (y/n) " RESP
		done

		if [[ "${RESP}" =~ [yY] ]]; then
			NUM_USB="$(ls /dev/ttyUSB* | wc -l)"
			if [[ "$NUM_USB" -eq 0 ]]; then
				echo "Error: no /dev/ttyUSB* devices present, but board appears in 'lsusb'"
				exit 1
			elif [[ "$NUM_USB" -eq 1 ]]; then
				KLIPPER_SERIAL="/dev/ttyUSB*"
			else
				USB_DEV=""
				while ! ( [[ "${USB_DEV}" =~ [0-9]+ ]] && [ "$USB_DEV" -gt 0 ] && [ "$USB_DEV" -le $NUM_USB ] ); do
					mapfile -t DEVICES < <(ls /dev/ttyUSB*)
					echo ${#DEVICES[@]}
					i=0
					while [ $i -lt ${#DEVICES[@]} ]; do
						printf "%d: %s\n" $((i+1)) ${DEVICES[$i]} 
						((++i))
					done
					read -p "Which USB device is the motor control board? (1-${NUM_USB}) " USB_DEV
				done
				KLIPPER_SERIAL="${DEVICES[$((USB_DEV-1))]}"
			fi
		fi
	fi
}

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
[Service]
ExecStart=${PWD}/backend.py
EOF
	sudo systemctl daemon-reload 
	sudo systemctl enable --now mapt
)}

get_config
install_klipper
install_mapt

echo
echo Finished installing MAPT.
