## indigo-omnilink
An Indigo Domotics plugin to enable Indigo to communicate over Ethernet with HAI/Leviton Omni systems.

This plugin is a work in progress. Please only use it if you don't mind using software that is partially complete, subject to change and undoubtedly buggy. I've been working with it on OS X El Capitan, Indigo versions 6.1.4-6.1.7, and have tried it with an Omni IIe running firmware version 3.15 and an Omni LTe with firmware version 3.12.

Omni systems have many more capabilities than I knew about when I started this project. So far the plugin can gather information from the controller, monitor the status of its security zones, and turn control units on and off.

### Before you start

If your Omni system is running an old firmware version, it may not be able to communicate over the Ethernet, in spite of having an Ethernet connector on the board. My ten-year old Omni IIe board was running version 2.12 which did not have Ethernet support and I was able to purchase version 3.15 in chip format from homecontrols.com.

According to a HAI press release which I found on Google, Ethernet support was a new feature in firmware version 2.4.

More recent Omni systems upgrade their firmware by download instead of by chip.

Once you have checked or updated your firmware, use your Omni keypad to go into the Setup menu and find the settings for IP Address, port and encryption keys. You should set the IP address to a unique address on your home network, and copy down the port number and encryption keys because you will need to type them into Indigo.  If you or the installer of your system have set up Leviton's Snap-Link app, this plugin uses the same configuration information as Snap-Link.

The plugin beginning with version 0.3.0 will store your encryption key in your keychain.

### Installing the plugin

[Download the (zip archive of the) plugin here](https://github.com/gazally/indigo-omnilink/archive/master.zip)

[Follow the plugin installation instructions](http://wiki.indigodomo.com/doku.php?id=indigo_6_documentation:getting_started#installing_plugins_and_configuring_plugin_settings_pro_only_feature)

### Creating devices for your Omni System

From the Indigo main window, choose Devices and then New... On the Device Type List, choose OmniLink, and the OmniLink device configuration window will pop up. Enter the IP Address, port number and two encryption keys that you copied down from your Omni keypad, and press the Connect button. If you got that all correct and your firmware version is new enough and your Omni board is actually plugged into your router, then the available device types should appear in your Device Types list. Select Controller to create a main device for your system, Zone to create devices for your security system zones, and Unit if you want devices for your light switches and relays. After you have made your selections, choose the Create Devices button.

### Acknowledgements

This plugin was made possible by the **jomnilinkII** library, created by Digital Dan.
