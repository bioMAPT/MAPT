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
	cat scripts/klipper-mcu.service <<< "User=${USER}" | sudo tee /etc/systemd/system/klipper-mcu.service >/dev/null
	sudo systemctl daemon-reload
 	sudo systemctl enable --now klipper-mcu

	# install klipper to control board
	if [ -c ${KLIPPER_SERIAL} ]; then
		echo "CONFIG_MACH_atmega1284p=y" > .config
		make olddefconfig
		make -j$(nproc)
		make flash FLASH_DEVICE="${KLIPPER_SERIAL}"
	fi
)}

install_mapt(){(
	sudo apt install -y python3-serial python3-flask python3-picamera2 python3-waitress authbind

	# install the klipper config
	ln -s ${PWD}/klipper.cfg ${HOME}/printer.cfg

	# configure authbind
	sudo touch /etc/authbind/byport/80
	sudo chmod 777 /etc/authbind/byport/80

	# set the hostname
	if [ "$(hostname)" == "raspberrypi" ]; then
		for f in /etc/hostname /etc/hosts; do sudo sed -r -i 's/raspberrypi/mapt/g' $f; done
	fi

	# install the systemd service
	sudo tee /etc/systemd/system/mapt.service >/dev/null <<EOF
[Unit]
Requires=klipper.service

[Install]
WantedBy=multi-user.target

[Service]
User=${USER}
Environment=PYTHONPATH=${PWD}
ExecStart=authbind python -m mapt
EOF

	sudo systemctl daemon-reload 
	sudo systemctl enable --now mapt
)}

install_klipper
install_mapt

echo
echo "Finished installing MAPT. The raspberry pi will now reboot. Wait 2 minutes, then navigate to http://$(hostname).local/ from a device on the same wifi network."
sudo reboot
