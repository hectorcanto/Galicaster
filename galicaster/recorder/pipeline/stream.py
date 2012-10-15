# -*- coding:utf-8 -*-
# Galicaster, Multistream Recorder and Player
#
#       galicaster/recorder/pipeline/stream
#
# Copyright (c) 2011, Teltek Video Research <galicaster@teltek.es>
#
# This work is licensed under the Creative Commons Attribution-
# NonCommercial-ShareAlike 3.0 Unported License. To view a copy of
# this license, visit http://creativecommons.org/licenses/by-nc-sa/3.0/
# or send a letter to Creative Commons, 171 Second Street, Suite 300,
# San Francisco, California, 94105, USA.

import logging
import gobject
import gst
import re

from os import path

from galicaster.recorder import base
from galicaster.recorder import module_register

class_name= 'stream'
encoder = ' x264enc pass=5 quantizer=22 speed-preset=4 profile=1 ! queue ! avimux ! '
sink = ' queue ! multifilesink name=gc-{0}-sink async=false next-file=discont post-messages=true'
sink2 = ' queue ! filesink name=gc-{0}-sink async=false '



pipestr = """
 v4l2src name=gc-{0}-src ! capsfilter name=gc-{0}-filter ! gc-{0}-dec
 videorate ! capsfilter name=gc-{0}-vrate ! videocrop name=gc-{0}-crop ! 
 tee name=tee-first  ! queue !  xvimagesink async=false qos=false name=gc-{0}-preview
 tee-first. ! queue ! valve drop=false name=gc-{0}-shift-even ! identity name=id-even 
 tee-first. ! queue ! valve drop=false name=gc-{0}-shift-odd ! identity name=id-odd 

""".format(class_name)

# xvidenc bitrate=50000000 ! queue ! avimux ! 

class GCstream(gst.Bin, base.Base):
    """
    This is a variation of the regular v4l2 plugin, suitable for uvc webcams, to stream continuosly while recording multifiles
    """


    order = ["name","flavor","location","file","caps", 
             "videocrop-left","videocrop-right", "videocrop-top", "videocrop-bottom"]
    gc_parameters = {
        "name": {
            "type": "text",
            "default": "Webcam",
            "description": "Name assigned to the device",
            },
        "flavor": {
            "type": "flavor",
            "default": "presenter",
            "description": "Matterhorn flavor associated to the track",
            },
        "location": {
            "type": "device",
            "default": "/dev/webcam",
            "description": "Device's mount point of the MPEG output",
            },
        "file": {
            "type": "text",
            "default": "CAMERA.avi",
            "description": "The file name where the track will be recorded.",
            },
        "caps": {
            "type": "caps",
            "default": "image/jpeg,framerate=10/1,width=640,height=480", 
            "description": "Forced capabilities",
            },
        "videocrop-right": {
            "type": "integer",
            "default": 0,
            "range": (0,200),
            "description": "Right  Cropping",
            },
        "videocrop-left": {
            "type": "integer",
            "default": 0,
            "range": (0,200),
            "description": "Left  Cropping",
            },
        "videocrop-top": {
            "type": "integer",
            "default": 0,
            "range": (0,200),
            "description": "Top  Cropping",
            },
        "videocrop-bottom": {
            "type": "integer",
            "default": 0,
            "range": (0,200),
            "description": "Bottom  Cropping",
            },
        }
           
    is_pausable = True
    has_audio   = False
    has_video   = True

    __gstdetails__ = (
        "Galicaster {0} Bin".format(class_name),
        "Generic/Video",
        "Generice bin to v4l2 interface devices",
        "Teltek Video Research",
        )

    def __init__(self, options={}):
        base.Base.__init__(self, options)
        gst.Bin.__init__(self, self.options['name'])

        self.file_number=0
        
        aux = pipestr.replace('gc-{0}-preview'.format(class_name), 'sink-' + self.options['name'])
        if 'image/jpeg' in self.options['caps']:
            aux = aux.replace('gc-{0}-dec'.format(class_name), 'jpegdec ! queue !')
        else:
            aux = aux.replace('gc-{0}-dec'.format(class_name), '')
                              
        bin = gst.parse_bin_from_description(aux, False)
        self.bin_start=bin
        
        branch1=RecordBranch(
            'even',
            path.join(self.options['path'],str(self.file_number)+self.options['file']))
        self.file_number+=1
        
        branch2=RecordBranch(
            'odd',
            path.join(self.options['path'],str(self.file_number)+self.options['file']))
        self.file_number+=1
        
        self.add(branch1)
        self.add(branch2)
        self.add(bin)

        self.set_option_in_pipeline('location', 'gc-{0}-src'.format(class_name), 'device')

        id1= self.get_by_name('id-even')
        bin.add_pad(gst.GhostPad('gp1', id1.get_pad('src')))
        bin.link(branch1)

        id2= self.get_by_name('id-odd')
        bin.add_pad(gst.GhostPad('gp2', id2.get_pad('src')))
        bin.link(branch2)

        # Prepare caps and crop
       
        self.set_option_in_pipeline('caps', 'gc-{0}-filter'.format(class_name), 'caps', gst.Caps)
        fr = re.findall("framerate *= *[0-9]+/[0-9]+", self.options['caps'])
        if fr:
            newcaps = 'video/x-raw-yuv,' + fr[0]
            self.set_value_in_pipeline(newcaps, 'gc-{0}-vrate'.format(class_name), 'caps', gst.Caps)
            #element2 = self.get_by_name('gc-{0}-vrate')
            #element2.set_property('caps', gst.Caps(newcaps))

        for pos in ['right','left','top','bottom']:
            self.set_option_in_pipeline('videocrop-'+pos, 'gc-{0}-crop'.format(class_name), pos, int)
            #element = self.get_by_name('gc-{0}-crop')
            #element.set_property(pos, int(self.options['videocrop-' + pos]))


    def cutFile(self):

        if self.file_number%2: # odd 1 3 5
            self.changeShift(True,'odd')
            self.changeShift(False,'even')
            branch_type='odd'

        else: # even 0 2 4
            self.changeShift(True,'even')
            self.changeShift(False,'odd')
            branch_type='even'

        identity= self.get_by_name('id-{0}'.format(branch_type))
        a = gst.structure_from_string('close_file')
        event = gst.event_new_custom(gst.EVENT_EOS, a)
        branch=self.get_by_name(branch_type)
        branch.send_event(event) 
        branch.set_state(gst.STATE_NULL)sprints
        self.bin_start.unlink(branch)
        self.remove(branch)
        location=path.join(self.options['path'],str(self.file_number)+self.options['file'])
        self.file_number+=1
        new_branch = RecordBranch(branch_type,location)
        self.add(new_branch)
        self.bin_start.link(new_branch)
        new_branch.set_state(gst.STATE_PLAYING)



    def changeShift(self, value, valve):
        valve1=self.get_by_name('gc-{0}-shift-{1}'.format(class_name,valve))
        valve1.set_property('drop', value)

    def changeValve(self, value):     
        valve1=self.get_by_name('gc-{0}-shift-even'.format(class_name))
        valve1.set_property('drop', value)
        if value:
            valve1=self.get_by_name('gc-{0}-shift-odd'.format(class_name))
            valve1.set_property('drop', value)

    def getVideoSink(self):
        return self.get_by_name('gc-{0}-preview'.format(class_name))
    
    def getSource(self):
        return self.get_by_name('gc-{0}-src'.format(class_name)) 

    def send_event_to_src(self, event):
        src1 = self.get_by_name('gc-{0}-src'.format(class_name))
        src1.send_event(event)


class RecordBranch(gst.Bin):

    def __init__(self, name, location):
        
        # ffmpegcolorspace ! queue ! x264enc ! queue ! avimux ! queue ! filesink
        gst.Bin.__init__(self, name)        
        cp1 = gst.element_factory_make('ffmpegcolorspace', 'cp1-'+name)
        q1 =  gst.element_factory_make('queue', 'q1-'+name)
        encoder = gst.element_factory_make('x264enc', 'enc-'+name)
        encoder.set_property('pass',5)
        encoder.set_property('quantizer',22)
        encoder.set_property('speed-preset',4)
        encoder.set_property('profile',1)
        q2 =  gst.element_factory_make('queue', 'q2-'+name)
        muxer = gst.element_factory_make('avimux', 'mux-'+name)
        q3 =  gst.element_factory_make('queue', 'q3-'+name)
        sink = gst.element_factory_make('filesink', 'sink'+name)
        sink.set_property('async',False)
        sink.set_property('location',location)

        elements=[cp1,q1,encoder,q2,muxer,q3,sink]
        for element in elements:
            self.add(element)    
        for i,element in enumerate(elements):
            if i<(len(elements)-1):
                element.link(elements[i+1])

        self.add_pad(gst.GhostPad('rb', cp1.get_static_pad('sink')))

gobject.type_register(GCstream)
gst.element_register(GCstream, 'gc-tream-bin')
module_register(GCstream, 'stream')
