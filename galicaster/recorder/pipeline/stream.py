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

#regular+stream1 = pulse+v4l OK
#regular+stream2 = pulse+v4l+videotest NO_LINK
regular = """
 v4l2src name=gc-{0}-src ! capsfilter name=gc-{0}-filter ! gc-{0}-dec
 videorate ! capsfilter name=gc-{0}-vrate ! videocrop name=gc-{0}-crop ! 
 tee name=tee-first ! queue !  xvimagesink async=false qos=false name=gc-{0}-preview
 tee-first. ! queue ! valve drop=false name=gc-{0}-shift-even ! identity name=id-even 
 pulsesrc name=gc-{0}-audio-src ! audioamplify name=gc-{0}-amplify amplification=1 ! 
 tee name=tee-aud ! queue ! level name=gc-{0}-level message=true interval=100000000 ! 
 volume name=gc-{0}-volume ! alsasink sync=false name=gc-{0}-audio-preview 
 tee-aud. ! queue ! audioconvert ! audiorate ! audioresample ! faac bitrate=96000 ! 
 audio/mpeg,mpegversion=4,stream-format=raw ! mux.
 tee-aud. ! valve drop=false name=gc-{0}-shift-audio ! identity name=id-audio 
""".format(class_name)

stream1= """ 
 tee-first. ! queue ! ffmpegcolorspace !
 x264enc pass=pass1 threads=2 bitrate=400 tune=zerolatency ! queue ! flvmux name=mux ! 
 queue ! rtmpsink name=gc-{0}-streaming-snk location='rtmp://172.20.209.171/live/cmar 
""".format(class_name)

stream2 = """ 
 videotestsrc name=gc-{0}-test ! video/x-raw-yuv,width=640,height=480,framerate=25/1 !
 tee name=tee-second ! queue ! aspectratiocrop aspect=4/3 ! mix.sink_0
 tee-second. ! queue ! fakesink silent=True
 videomixer2 name=mix background=1 
      sink_0::xpos=0 sink_0::ypos=120 sink_0::zorder=0 
      sink_1::xpos=640 sink_1::ypos=120 sink_1::zorder=0 !
 ffmpegcolorspace !  x264enc pass=pass1 threads=2 bitrate=400 tune=zerolatency ! queue ! 
 flvmux name=mux ! queue ! rtmpsink name=gc-{0}-streaming location='rtmp://172.20.209.171/live/cmar
 tee-first. ! queue ! aspectratiocrop=4/3 ! videoscale ! videorate ! ffmpegcolorspace ! 
 video/x-raw-yuv, format=(fourcc)AYUV, framerate=25/1, width=640, height=480 ! mix.sink_1 
""".format(class_name)

streaming = "x264enc pass=pass1 threads=0 bitrate=400 tune=zerolatency"

pipestr = """
 v4l2src name=gc-{0}-src ! capsfilter name=gc-{0}-filter ! gc-{0}-dec
 videorate ! capsfilter name=gc-{0}-vrate ! videocrop name=gc-{0}-crop ! 
 tee name=tee-first ! queue !  xvimagesink sync=false qos=false name=gc-{0}-preview
 tee-first. ! queue ! valve drop=false name=gc-{0}-shift-even ! identity name=id-even 
 tee-first. ! queue ! aspectratiocrop aspect-ratio=4/3 ! videoscale ! videorate ! ffmpegcolorspace !
 video/x-raw-yuv,format=(fourcc)AYUV,framerate=25/1,width=640,height=480 ! mix.sink_1 

 v4l2src name=gc-{0}-src2 ! capsfilter name=gc-{0}-2filter ! gc-{0}-2dec
 videorate ! capsfilter name=gc-{0}-vrate2 ! videocrop name=gc-{0}-crop2 ! 
 tee name=tee-second ! queue !  xvimagesink sync=false qos=false name=gc-{0}-preview2
 tee-second. ! queue ! valve drop=false name=gc-{0}-shift-odd ! identity name=id-odd
 tee-second. ! queue ! aspectratiocrop aspect-ratio=4/3 ! videoscale ! videorate ! ffmpegcolorspace !
 video/x-raw-yuv,format=(fourcc)AYUV,framerate=25/1,width=640,height=480 ! mix.sink_0

 pulsesrc name=gc-{0}-audio-src ! audioamplify name=gc-{0}-amplify amplification=1 ! 
 tee name=tee-aud ! queue ! level name=gc-{0}-level message=true interval=100000000 ! 
 volume name=gc-{0}-volume ! alsasink sync=false name=gc-{0}-audio-preview 
 tee-aud. ! queue ! audioconvert ! audiorate ! audioresample ! faac bitrate=96000 ! 
 audio/mpeg,mpegversion=4,stream-format=raw ! mux.
 tee-aud. ! queue ! valve drop=false name=gc-{0}-shift-audio ! identity name=id-audio 

 videomixer2 name=mix background=1 
   sink_0::xpos=0 sink_0::ypos=120 sink_0::zorder=0 
   sink_1::xpos=640 sink_1::ypos=120 sink_1::zorder=0 !
 ffmpegcolorspace ! {1} ! queue ! 
 flvmux name=mux ! queue ! rtmpsink name=gc-{0}-streaming location='rtmp://172.20.209.171/live/cmar
""".format(class_name,streaming)

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
        "vumeter": {
            "type": "boolean",
            "default": "True",
            "description": "Activate Level message",
            },
        "player": {
            "type": "boolean",
            "default": "True",
            "description": "Enable sound play",
            },
        "amplification": {
            "type": "float",
            "default": 1.0,
            "range": (0,10),
            "description": "Audio amplification",
      },


        }
           
    is_pausable = False
    has_audio   = True
    has_video   = True
    has_stream = True

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

        if 'image/jpeg' in self.options['caps2']:
            aux = aux.replace('gc-{0}-2dec'.format(class_name), 'jpegdec ! queue !')
        else:
            aux = aux.replace('gc-{0}-2dec'.format(class_name), '')
                              
        bin = gst.parse_bin_from_description(aux, False)
        self.bin_start=bin

        self.placeBranchs(bin)
        print self
        print dir(self)
        print self.get_path_string()
        
  
        # Prepare caps and crop       
        self.set_option_in_pipeline('caps', 'gc-{0}-filter'.format(class_name), 'caps', gst.Caps)
        self.set_option_in_pipeline('caps2', 'gc-{0}-2filter'.format(class_name), 'caps', gst.Caps)

        fr = re.findall("framerate *= *[0-9]+/[0-9]+", self.options['caps'])
        if fr:
            newcaps = 'video/x-raw-yuv,' + fr[0]
            self.set_value_in_pipeline(newcaps, 'gc-{0}-vrate'.format(class_name), 'caps', gst.Caps)

        fr = re.findall("framerate *= *[0-9]+/[0-9]+", self.options['caps2'])
        if fr:
            newcaps = 'video/x-raw-yuv,' + fr[0]
            self.set_value_in_pipeline(newcaps, 'gc-{0}-vrate2'.format(class_name), 'caps', gst.Caps)


        for pos in ['right','left','top','bottom']:
            self.set_option_in_pipeline('videocrop-'+pos, 'gc-{0}-crop'.format(class_name), pos, int)


        if "player" in self.options and self.options["player"] == False:
            self.mute = True
            element = self.get_by_name("gc-{0}-volume".format(class_name))
            element.set_property("mute", True)
        else:
            self.mute = False

        if "vumeter" in self.options:
            level = self.get_by_name("gc-{0}-level".format(class_name))
            if self.options["vumeter"] == False:
                level.set_property("message", False) 
        if "amplification" in self.options:
            ampli = self.get_by_name("gc-{0}-amplify".format(class_name))
            ampli.set_property("amplification", float(self.options["amplification"]))

    def placeBranchs(self, main):

        branch1=RecordBranch(
            'even',
            #path.join(self.options['path'],str(self.file_number)+self.options['file']),
            path.join(self.options['path'],self.options['file']),
            )

        branch2=RecordBranch(
            'odd',
            path.join(self.options['path'],self.options['file2']),
            )
        
        audio1=AudioBranch(
            'audio',
            path.join(self.options['path'],"sound.mp3")
            )        
        
        self.add(branch1)
        self.add(branch2)
        self.add(audio1)
        self.add(main)

        self.set_option_in_pipeline('location', 'gc-{0}-src'.format(class_name), 'device')
        self.set_option_in_pipeline('location2', 'gc-{0}-src2'.format(class_name), 'device')

        id1= self.get_by_name('id-even')
        main.add_pad(gst.GhostPad('gp1', id1.get_pad('src')))
        main.link(branch1)

        id2= self.get_by_name('id-odd')
        main.add_pad(gst.GhostPad('gp2', id2.get_pad('src')))
        main.link(branch2)

        id3= self.get_by_name('id-audio')
        main.add_pad(gst.GhostPad('gp3', id3.get_pad('src')))
        main.link(audio1)

    def cutFile(self):

        branchs = ['even','odd','audio']
        elements = []
        for branch in branchs:
            elements+=[self.get_by_name(branch)]

        a = gst.structure_from_string('close_file')
        event = gst.event_new_custom(gst.EVENT_EOS, a)


        for branch in branchs:
            self.changeShift(True,branch) #close valves
            
        # send eos and remove branch
        for branch in elements:
            branch.send_event(event) 

        for branch in elements:
            branch.set_state(gst.STATE_NULL)
        element[0].get_state()
        
        for branch in elements:
            self.bin_start.unlink(branch)      

        for branch in elements:
            self.remove(branch)

        #reinstate branch
        
        location=path.join(self.options['path'],str(self.file_number)+self.options['file'])
        location2=path.join(self.options['path'],str(self.file_number)+self.options['file2'])
        location3=path.join(self.options['path'],str(self.file_number)+"sound.mp3")
        self.file_number+=1
        new_branch = RecordBranch(branchs[0],location)
        new_branch2 = RecordBranch(branchs[1],location2)
        new_audio = AudioBranch(branchs[2],location3)
        self.add(new_branch)
        self.add(new_branch2)
        self.add(new_audio)
        self.bin_start.link(new_branch)
        self.bin_start.link(new_branch2)
        self.bin_start.link(new_audio)
        new_branch.set_state(gst.STATE_PLAYING)
        new_branch.set_state(gst.STATE_PLAYING2)
        new_audio.set_state(gst.STATE_PLAYING)
        self.changeShift(False,branchs[0])
        self.changeShift(False,branchs[1])
        self.changeShift(False,branchs[2])



    def changeShift(self, value, valve):
        valve1=self.get_by_name('gc-{0}-shift-{1}'.format(class_name,valve))
        valve1.set_property('drop', value)

    def changeValve(self, value):     
        valve1=self.get_by_name('gc-{0}-shift-even'.format(class_name))
        valve2=self.get_by_name('gc-{0}-shift-odd'.format(class_name))
        valve3=self.get_by_name('gc-{0}-shift-audio'.format(class_name))
        valve1.set_property('drop', value)
        valve2.set_property('drop', value)
        valve3.set_property('drop', value)

        #if value:
        #    valve1=self.get_by_name('gc-{0}-shift-odd'.format(class_name))
        #    valve1.set_property('drop', value)

    def changeStream(self, value):     
        valve1=self.get_by_name('gc-{0}-valve-stream'.format(class_name))
        #valve1.set_property('drop', value)

    def getVideoSink(self):
        return self.get_by_name('gc-{0}-preview'.format(class_name))
    
    def getSource(self):
        return self.get_by_name('gc-{0}-src'.format(class_name)) 

    def send_event_to_src(self, event):
        src1 = self.get_by_name('gc-{0}-src'.format(class_name))
        src2 = self.get_by_name('gc-{0}-src2'.format(class_name))
        src3 = self.get_by_name('gc-{0}-audio-src'.format(class_name))
        src1.send_event(event)
        src2.send_event(event)
        src3.send_event(event)

    def getAudioSink(self):
        return self.get_by_name('gc-{0}-audio-preview'.format(class_name))

    def mute_preview(self, value):
        if not self.mute:
            element = self.get_by_name("gc-{0}-volume".format(class_name))
            element.set_property("mute", value)

    def update_bins_desc(self, desc):

        options = desc[0]
        new={}
        modified = {}
        for key,value in options.iteritems():
            if key.count('2'):
                new[key[:len(key)-1]]=value
            else:
                modified[key]=value
        new['path']=options['path']
        new['device']='v4l2'

        audio = {}    
        for key in ['vumeter','flavor','amplification','player','path']:
            audio[key]=options[key]
        audio['file']='sound.mp3'
        audio['location']='default'
        audio['device']='pulse'
        
        desc=[modified,new,audio]
        return desc

class RecordBranch(gst.Bin):

    def __init__(self, name, location):
        
        # ffmpegcolorspace ! queue ! x264enc ! queue ! avimux ! queue ! filesink
        gst.Bin.__init__(self, name)        
        cp1 = gst.element_factory_make('ffmpegcolorspace', 'cp1-'+name)
        q1 =  gst.element_factory_make('queue', 'q1-'+name)
        #options={'pass':'pass1','threads':0,'bitrate':400,'tune':'zerolatency'}
        #encoder = self.make_encoder('x264enc',name,options)
        options={'quantizer':4, 'gop-size':1, 'bitrate':10000000 }
        encoder = self.make_encoder('ffenc_mpeg2video',name,options)
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

    def make_encoder(self,enc_type,name,options):
        encoder = gst.element_factory_make(enc_type, 'enc-'+name)
        for key,value in options.iteritems():
            encoder.set_property(key,value)
                                 
        return encoder



class AudioBranch(gst.Bin):
    def __init__(self, name, location):
        # audioconvert ! lamemp3enc ! queue ! filesink 
        gst.Bin.__init__(self, name)        
        ac = gst.element_factory_make('audioconvert', 'audioconvert-'+name)
        audioenc = gst.element_factory_make('lamemp3enc', 'audioenc-'+name)
        audioenc.set_property('target',1)
        audioenc.set_property('bitrate',192)
        audioenc.set_property('cbr',True)
        q4 = gst.element_factory_make('queue', 'q4-'+name)
        audiosink = gst.element_factory_make('filesink', 'audiosink-'+name)
        audiosink.set_property('async',False)
        audiosink.set_property('location',location)

        elements=[ac,audioenc,q4,audiosink]
        for element in elements:
            self.add(element)    
        for i,element in enumerate(elements):
            if i<(len(elements)-1):
                element.link(elements[i+1])

        self.add_pad(gst.GhostPad('audiorb', ac.get_static_pad('sink')))

gobject.type_register(GCstream)
gst.element_register(GCstream, 'gc-stream-bin')
module_register(GCstream, 'stream')
