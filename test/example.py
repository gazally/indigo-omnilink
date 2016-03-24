from __future__ import unicode_literals
from __future__ import print_function

from time import sleep

from py4j.java_gateway import JavaGateway, CallbackServerParameters

class NotificationListener(object):
    def __init__(self, Message):
        self.messages = {Message.OBJ_TYPE_AREA: "STATUS_AREA changed",
                         Message.OBJ_TYPE_AUDIO_ZONE: "STATUS_AUDIO_ZONE changed",
			 Message.OBJ_TYPE_AUX_SENSOR: "STATUS_AUX changed",
			 Message.OBJ_TYPE_EXP: "STATUS_EXP changed",
			 Message.OBJ_TYPE_MESG: "STATUS_MESG changed",
			 Message.OBJ_TYPE_THERMO: "STATUS_THERMO changed",
			 Message.OBJ_TYPE_UNIT: "STATUS_UNIT changed",
			 Message.OBJ_TYPE_ZONE: "STATUS_ZONE changed"
                         }

    def objectStausNotification(self, status):
        print(self.messages.get(status.getStatusType(),
                                "Unknown type {0}".format(status.getStatusType())))
        statuses = status.getStatuses()
        for s in statuses:
            print(s.toString())

    def otherEventNotification(self, other): #OtherEventNotifications
        print("otherEventNotification")

    class Java:
        implements = ['com.digitaldan.jomnilinkII.NotificationListener']


class DisconnectListener(object):
    def notConnectedEvent(self, e):
        print("notConnectedEvent")
    class Java:
        implements = ['com.digitaldan.jomnilinkII.DisconnectListener']

def query_and_print(c, objtype, mtype, filter1, filter2, filter3):
    objnum = 0
    while True:
        m = c.reqObjectProperties(objtype, objnum, 1, filter1, filter2, filter3)
        if m.getMessageType() != mtype:
            break
	print(m.toString())
	objnum = m.getNumber()
        status = c.reqObjectStatus(objtype, objnum, objnum)
        statuses = status.getStatuses()
        for s in statuses:
            print(s.toString())


        
def main():
    gateway = JavaGateway(start_callback_server=True,
                          callback_server_parameters=CallbackServerParameters())
    jomnilinkII = gateway.jvm.com.digitaldan.jomnilinkII
    Message = jomnilinkII.Message
    ObjectProperties = jomnilinkII.MessageTypes.ObjectProperties

    with open("omni.txt", "r") as keyfile:
        # In order to test communication with your omni system, put its
        # connection parameters (ip address, port, encryption key) in a
        # three line text file called omni.txt in the test directory
        lines = keyfile.readlines()
        ip = lines[0].strip()
        port = int(lines[1].strip())
        encoding = lines[2].strip()

    c = jomnilinkII.Connection(ip, port, encoding)
    c.setDebug(True)
    c.addNotificationListener(NotificationListener(Message))
    c.addDisconnectListener(DisconnectListener())
    c.enableNotifications()

    print(c.reqSystemInformation().toString())
    print(c.reqSystemStatus().toString())
    print(c.reqSystemTroubles().toString())
    print(c.reqSystemFormats().toString())
    print(c.reqSystemFeatures().toString())

    print("Max zones", c.reqObjectTypeCapacities(Message.OBJ_TYPE_ZONE).getCapacity())
    print("Max units", c.reqObjectTypeCapacities(Message.OBJ_TYPE_UNIT).getCapacity())
    print("Max areas", c.reqObjectTypeCapacities(Message.OBJ_TYPE_AREA).getCapacity())
    print("Max buttons", c.reqObjectTypeCapacities(Message.OBJ_TYPE_BUTTON).getCapacity())
    print("Max codes", c.reqObjectTypeCapacities(Message.OBJ_TYPE_CODE).getCapacity())
    print("Max thermos", c.reqObjectTypeCapacities(Message.OBJ_TYPE_THERMO).getCapacity())
    print("Max mesgs", c.reqObjectTypeCapacities(Message.OBJ_TYPE_MESG).getCapacity())
    print("Max audio_zones", c.reqObjectTypeCapacities(Message.OBJ_TYPE_AUDIO_ZONE).getCapacity())
    print("Max audio_sources", c.reqObjectTypeCapacities(Message.OBJ_TYPE_AUDIO_SOURCE).getCapacity())

    print(c.reqObjectTypeCapacities(Message.OBJ_TYPE_AUDIO_SOURCE).toString())
    print(c.reqObjectTypeCapacities(Message.OBJ_TYPE_AUDIO_ZONE).toString())

    query_and_print(c, Message.OBJ_TYPE_ZONE, Message.MESG_TYPE_OBJ_PROP,
		    ObjectProperties.FILTER_1_NAMED,
                    ObjectProperties.FILTER_2_AREA_ALL,
                    ObjectProperties.FILTER_3_ANY_LOAD)

    query_and_print(c, Message.OBJ_TYPE_AREA, Message.MESG_TYPE_OBJ_PROP,
		    ObjectProperties.FILTER_1_NAMED_UNAMED,
                    ObjectProperties.FILTER_2_NONE,
                    ObjectProperties.FILTER_3_NONE)

    query_and_print(c, Message.OBJ_TYPE_UNIT, Message.MESG_TYPE_OBJ_PROP,
		    ObjectProperties.FILTER_1_NAMED,
                    ObjectProperties.FILTER_2_AREA_ALL,
                    ObjectProperties.FILTER_3_ANY_LOAD)

    query_and_print(c, Message.OBJ_TYPE_BUTTON, Message.MESG_TYPE_OBJ_PROP,
		    ObjectProperties.FILTER_1_NAMED,
                    ObjectProperties.FILTER_2_AREA_ALL,
                    ObjectProperties.FILTER_3_NONE)

    query_and_print(c, Message.OBJ_TYPE_CODE, Message.MESG_TYPE_OBJ_PROP,
		    ObjectProperties.FILTER_1_NAMED,
                    ObjectProperties.FILTER_2_AREA_ALL,
                    ObjectProperties.FILTER_3_NONE)

    query_and_print(c, Message.OBJ_TYPE_THERMO, Message.MESG_TYPE_OBJ_PROP,
		    ObjectProperties.FILTER_1_NAMED,
                    ObjectProperties.FILTER_2_AREA_ALL,
                    ObjectProperties.FILTER_3_NONE)

    query_and_print(c, Message.OBJ_TYPE_AUX_SENSOR, Message.MESG_TYPE_OBJ_PROP,
		    ObjectProperties.FILTER_1_NAMED,
                    ObjectProperties.FILTER_2_AREA_ALL,
                    ObjectProperties.FILTER_3_NONE)

    num = 0
    count = 0
    while True:
        m = c.uploadEventLogData(num, 1)
        if m.getMessageType() != Message.MESG_TYPE_EVENT_LOG_DATA or count > 10:
            break
	print(m.toString())
	num = m.getEventNumber()
	count += 1

    print(c.uploadNames(Message.OBJ_TYPE_UNIT, 0).toString())

    for i in range(1, 10000):
        s = [ord(ch) - ord("0") for ch in "{0:04}".format(i)]
        for a in range(1, 3):
            scv = c.reqSecurityCodeValidation(a, *s)
            if scv.getAuthorityLevel() != 0:
                print("{0:04}/{1}: {2}", i, a, scv.toString())
			
    print("All Done, OmniConnection thread now running")
	
    while True:
        sleep(10)


if __name__ == "__main__":
    main()
    
    
