## indigo-omnilink
An Indigo Domotics plugin to enable Indigo to communicate over Ethernet with HAI/Leviton Omni systems.

This plugin is a work in progress. Please only use it if you don't mind using software that is partially complete, subject to change and undoubtedly buggy. The only configuration I've tried it on is OS X El Capitan and Indigo 6.1.4 talking to an Omni IIe running firmware version 3.15.

Omni systems have many more capabilities than I knew about when I started this project. So far the plugin can gather some basic info about the controller and monitor the status of its security zones.

### Before you start

If your Omni system is running an old firmware version, it may not be able to communicate over the Ethernet, in spite of having an Ethernet connector on the board. My ten-year old Omni IIe board was running version 2.12 which did not have Ethernet support and I was able to purchase version 3.15 in chip format from homecontrols.com. 

According to a HAI press release which I found on Google, Ethernet support was a new feature in firmware version 2.4. 

More recent Omni systems upgrade their firmware by download instead of by chip.

From your Omni keypad, go into the Setup menu and find the settings for IP Address, port and encryption keys. You should set the IP address to a unique address on your home network, and copy down the port number and encryption keys because you will need to type them into Indigo.

### Some installation requirements
The OmniLink plugin was made possible by a well-written open source library called **jomnilinkII**, which handles all the network communciation with the Omni system. But **jomnilinkII** is written in Java. This means that in order for the OmniLink plugin to work, you will need to install Java on your system as well as an external Python library called **py4j** which enables Python and Java to communicate with each other.

Java installations come in two flavors: Java in the browser and command-line Java, which is what the OmniLink plugin uses. In order to get Java on the command line you need to install the Java developer kit. If you haven't done this or haven't done it recently enough to have the current version, go to oracle.com, and from their menu choose Products, Developer Tools, and then Java SE JDK. Choose the version of the JDK they are currently recommending for Mac OS X in the dmg version.  After you run the Java installer, launch the Terminal app and at the `$` prompt type:

```sh
java -version
```

followed by the return key and it should tell you the version number you just installed.

In order to get **py4j**, the easiest option is to install it as part of Python 2.6, which is the version of Python that Indigo uses. This process does require some more Terminal commands. 

Easy Install is a program that comes with OS X that we can use to install python libraries. To get started, type this into Terminal:
```sh
sudo easy_install-2.6 pip
```
followed by return. When you enter this command you may be prompted for your password, so type your password, followed by return. Since Python 2.6 is actually a really old version of Python, Easy Install will give you scary-looking warnings, which you can probably ignore. 

Now you can install **py4j**:
```sh
sudo easy_install-2.6 pip py4j
```
followed by the return key. To test that your installation of **py4j** worked, type:
```sh
python2.6
```
followed by return at the `$` prompt. You will be presented with the python prompt `>>>`. Now type:
```
import py4j
``` 
followed by return and the `>>>` prompt should return with no messages or errors. Close Terminal, you're done!

### Installing the plugin

[Download the (zip archive of the) plugin here](https://github.com/gazally/indigo-omnilink/archive/master.zip)

[Follow the plugin installation instructions](http://wiki.indigodomo.com/doku.php?id=indigo_6_documentation:getting_started#installing_plugins_and_configuring_plugin_settings_pro_only_feature)


### Creating devices for your Omni System

From the Indigo main window, choose Devices and then New... On the Device Type List, choose OmniLink, and the OmniLink device configuration window will pop up. Enter the IP Address, port number and two encryption keys that you copied down from your Omni keypad, and press the Connect button. If you got that all correct and your firmware version is new enough and your Omni board is actually plugged into your router, then two things should appear in your Device Types list: Controller and Zone. Select both of those and choose the Create Devices button, and boom! All of your security zones are now Indigo devices.

