#!/bin/ksh
#
# Install Microbio Automatic Photography Tool firmware

# exit script on first error
set -e

install_klipper(){(
	# clone the klipper repo
	git clone --filter=tree:0 --branch=v0.12.0 https://github.com/Klipper3d/klipper.git 

	cd klipper

	# increase the timeouts to something more suitable for this application
	sed -r -i 's/TRSYNC_TIMEOUT = 0.025/TRSYNC_TIMEOUT = 0.25/' klippy/mcu.py
	sed -r -i 's/TRSYNC_SINGLE_MCU_TIMEOUT = 0.250/TRSYNC_SINGLE_MCU_TIMEOUT = 2.50/' klippy/mcu.py

	# update debian install script for bookworm
	sed -r -i 's/python-dev /python-dev-is-python3 /' scripts/install-debian.sh
	sed -r -i 's/python2/python3/' scripts/install-debian.sh

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
)}

install_mapt(){(
	# install the klipper config
	ln -s ${PWD}/klipper.cfg ${HOME}/printer.cfg

	# install the systemd service
	cat > /etc/systemd/system/mapt.service <<EOF
[Service]
ExecStart=${PWD}/backend.py
EOF
	sudo systemctl daemon-reload 
	sudo systemctl enable --now mapt
)}

install_klipper
#install_mapt
