package com.digitaldan.jomnilinkII.MessageTypes;


/**
*  Copyright (C) 2009  Dan Cunningham                                         
*                                                                             
* This program is free software; you can redistribute it and/or
* modify it under the terms of the GNU General Public License
* as published by the Free Software Foundation, version 2
* of the License, or (at your option) any later version.
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with this program; if not, write to the Free Software
* Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
*/

import com.digitaldan.jomnilinkII.Message;

public class ReqObjectTypeCapacities implements Message {

	private int objType;
	
	/*
	 *This message requests the HAI controller to report the number of objects of the specified type that the controller
supports.
         Start character          0x21
         Message length           0x02
         Message type             0x1E
         Data 1                   object type
         CRC 1                    varies
         CRC 2                    varies
         Expected reply:          OBJECT TYPE CAPACITIES

	 */
	
	public ReqObjectTypeCapacities(int objectType){
		objType = objectType;
	}
	
	public int getMessageType() {
		return MESG_TYPE_REQ_OBJ_CAPACITY;
	}
	
	public int objectType(){
		return objType;
	}

	public String toString() {
	    final String TAB = "    ";
	    String retValue = "";
	    
	    retValue = "ReqObjectTypeCapacities ( "
	        + "objType = " + this.objType + TAB
	        + " )";
	
	    return retValue;
	}

}
