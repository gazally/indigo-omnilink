all: MenuItems.xml Actions.xml Devices.xml Events.xml

ifneq ($(wildcard Device_*.xml),)
Devices.xml: Device_*.xml
	echo '<?xml version="1.0"?>' > Devices.xml
	echo '<Devices>' >> Devices.xml
	cat Device_*.xml >> Devices.xml
	echo '</Devices>' >> Devices.xml
endif

ifneq ($(wildcard Action_*.xml),)
Actions.xml: Action_*.xml
	echo '<?xml version="1.0"?>' > Actions.xml
	echo '<Actions>' >> Actions.xml
	cat Action_*.xml >> Actions.xml
	echo '</Actions>' >> Actions.xml
endif

ifneq ($(wildcard MenuItem_*.xml),)
MenuItems.xml: MenuItem_*.xml
	echo '<?xml version="1.0"?>' > MenuItems.xml
	echo '<MenuItems>' >> MenuItems.xml
	cat MenuItem_*.xml >> MenuItems.xml
	echo '</MenuItems>' >> MenuItems.xml
endif

ifneq ($(wildcard Event_*.xml),)
Events.xml: Event_*.xml
	echo '<?xml version="1.0"?>' > Events.xml
	echo '<Events>' >> Events.xml
	cat Event_*.xml >> Events.xml
	echo '</Events>' >> Events.xml
endif

