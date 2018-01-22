#!/usr/bin/env python
#
import time 
import hashlib
import json
import sys
import signal
import logging
import logging.handlers
import os
import hmac
import daemon
import setproctitle
import socket
import traceback
import linecache

import configargparse

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish

import MqttHandler

default_cnf_files = ["/usrlocal/etc/acnode.ini","/etc/acnode.ini","~/.acnode.ini", "acnode.ini"]
default_master = 'master'
default_node  = 'unamednode'
default_host = 'localhost'
default_sub = default_node
default_protocol = "publish.MQTTv311"
default_machine = 'deur'

class ACNodeBase:
  cnf = None
  topic = None
  logtopic = None
  logger = None
  protocol = None
  client = None
  parser = None
  commands = {}
  forever = 0
  default_pidfile = "/var/run/master.pid"
  looptimeout = 0.2

  def __init__(self,description='ACNodeBase', cnf_file=None):

    files = default_cnf_files
    if cnf_file: 
      files = (cnf_file)
    self.parser = configargparse.ArgParser(default_config_files=files)

    self.commands[ 'announce' ] = self.cmd_announce

  def parseArguments(self):
    self.parser.add('-c', '--config', is_config_file=True,  
         help='config file path (default is '+",".join(default_cnf_files)+').')

    self.parser.add('--master','-M',default=default_master,
         help='Name of the master node (default: '+default_master+')'),

    self.parser.add('--node','-n',default=default_node,
         help='Name of this node (default: '+default_node+')'),
    self.parser.add('--machine','-a',default=default_machine,
         help='Machine (default :'+default_machine+')'),

    self.parser.add('-m','--mqtthost',default=default_host,
         help='MQTT host (default :'+default_host+')'),
    self.parser.add('--mqttprotocol',default=default_protocol,
         help='MQTT protocol (default :'+default_protocol+')'),
    self.parser.add('--topic','-t',default=default_sub,
         help='MQTT topic to subcribe to for replies from the master (default: '+default_sub+').'),

    self.parser.add('--verbose', '-v', action='count', default=0,
         help='Verbose on (default off)')
    self.parser.add('--debug', '-d', action='count', default=0,
         help='Debuging on; implies verbose (default off)')
    self.parser.add('--no-mqtt-log', action='count',
         help='Disable logging to MQTT log channel (default on)'),
    self.parser.add('--no-syslog',  action='count',
        help='Disable syslogging (defautl on)'),
    self.parser.add('-l','--logfile', type=configargparse.FileType('w+'), 
        help='Append log entries to specified file (default: none)'),

    self.parser.add('--pidfile', action='store', default = self.default_pidfile,
         help='File to write PID to, (Default: '+self.default_pidfile+').')
    self.parser.add('--daemonize', '-b', action='count',
         help='Deamonize into the background after startup (default is to stay in the foreground).')

    self.cnf = self.parser.parse_args()

  def setup(self):
    setproctitle.setproctitle(self.cnf.node)

    loglevel=logging.ERROR

    if self.cnf.verbose:
        loglevel=logging.INFO
        FORMAT="%(asctime)s %(levelname)s %(message)s"

    if self.cnf.debug:
        loglevel=logging.DEBUG
        FORMAT="%(asctime)s %(levelname)s %(message)s\n\t%(pathname)s:%(lineno)d %(module)s %(funcName)s"

    logging.basicConfig(format=FORMAT)
    
    self.logger = logging.getLogger()
    self.logger.setLevel(loglevel)
    
    self.logtopic = self.cnf.topic + "/log/" + self.cnf.node
    if not self.cnf.no_mqtt_log:
      self.logger.addHandler(MqttHandler.MqttHandler(
        self.cnf.mqtthost, self.logtopic, protocol=self.cnf.mqttprotocol))

    if self.cnf.logfile:
      self.logger.addHandler(logging.StreamHandler(stream=self.cnf.logfile))

    # if self.cnf.verbose:
    #   self.logger.addHandler(logging.StreamHandler())

    if not self.cnf.no_syslog:
       self.logger.addHandler(logging.handlers.SysLogHandler())

    if not self.cnf.machine:
      self.cnf.machine = self.cnf.node

    # self.topic = self.cnf.topic+ "/" + self.cnf.master + "/" + self.cnf.node
    signal.signal(signal.SIGINT, self.end_read)
    signal.signal(signal.SIGQUIT, self.end_read)

  def protect_uid(self,target_node, uid):
      return "**-**-**-**"

  def send_request(self, command, target_node, target_machine, tag_uid):

      tag_encoded = self.protect_uid(target_node, tag_uid)

      data = command + " " + target_node + " " + target_machine + " " + tag_encoded
      self.send(self.cnf.master, data)
 
  def split_payload(self, msg):
    command = None

    try:
      elems = msg['payload'].split(' ')
      return(elems)

    except:
      self.logger.debug("Cannot parse payload '{}' ; ignored".format(payload))
      return None

    msg['elems'] = elems
    return None
 
  def send(self,dstnode,payload,raw=False):
      # traceback.print_stack()
      
      topic = self.cnf.topic+ "/" + dstnode + "/" + self.cnf.node

      self.logger.debug(">>>>Sending @"+topic+": "+payload)
      try:
         publish.single(topic, payload, hostname=self.cnf.mqtthost, protocol=self.cnf.mqttprotocol)
      except:
         self.logger.critical("Failed to send {}: '{}'".format(topic,payload));

  def announce(self,dstnode):
    return self.send(dstnode, "announce " + socket.gethostbyname(socket.gethostname()));

  def on_connect(self, client, userdata, flags, rc):
    self.logger.info("(re)Connected to '" + self.cnf.mqtthost + "'")
    if self.cnf.node == self.cnf.master:
      self.subscribe(client,self.cnf.node + "/#" )
    else:
      self.subscribe(client,self.cnf.node + "/" + self.cnf.master)

  def subscribe(self,client,leaf):
    topic = self.cnf.topic + "/" + leaf

    if sys.version_info[0] < 3:
       topic = topic.encode('ASCII')

    mid = client.subscribe(topic)
    self.logger.debug(("Subscription req to {0} MID={1}".format(topic, mid)))

  def on_subscribe(self, client, userdata, mid, granted_qos):
    self.logger.info("(re)Subscribed.")
    self.announce(self.cnf.master)

  def parse_topic(self, msg):
    try:
      msg['path'] = msg['topic'].split('/')
      msg['destination'] = msg['path'][-2]
      msg['node'] = msg['path'][-1]
    except Exception as e:
      self.logger.warning("Message topic '{}' could not be parsed: {} -- ignored.".format(msg['topic'],str(e)))
      return None
    
    return msg

  def cmd_announce(self,msg):
    # traceback.print_stack()

    # if it is not me
    if msg['node'] != self.cnf.node:
         self.logger.info("Announce of {} {}".format(msg['node'],msg['payload']))
    else:
       self.logger.debug("Ignoring my own restart/announce message.")

    return None
         
  def extract_validated_payload(self, msg):
    self.logger.debug("Unversioned payload (ignored): ".format(payload))
    return None

  def on_message(self,client, userdata, message):
    msg = {
        'topic': message.topic,
        'payload': None,
        'validated': 0


    }
    try:
      self.logger.debug("<<<<Reccing @"+message.topic+": "+message.payload.decode('ASCII'))
    except:
      pass

    if not self.parse_topic(msg):
        return None

    try:
        msg['payload'] = message.payload.decode('ASCII')
        
        if not self.extract_validated_payload(msg):
            return None

        cmd = msg['payload'].split(' ')[0]
    except Exception as e:
      self.logger.warning("Could not parse request {}:{}' -- ignored".format(message.payload, str(e)))
      if 1:
            exc_type, exc_obj, tb = sys.exc_info()
            f = tb.tb_frame
            lineno = tb.tb_lineno
            filename = f.f_code.co_filename
            linecache.checkcache(filename)
            line = linecache.getline(filename, lineno, f.f_globals)
            self.logger.debug('EXCEPTION IN ({}, LINE {} "{}"): {}'.format(filename, lineno, line.strip(), exc_obj))

      return None

    if cmd in self.commands:
        self.logger.debug("Handling command '{}' with {}:{}()".format(cmd,self.commands[cmd].__class__.__name__, self.commands[cmd].__name__))
        return self.commands[cmd](msg)

    self.logger.debug("No mapping for {} - deferring <{}> for handling by {}".format(cmd, msg['payload'],self.__class__.__name__))
    return None

  # Capture SIGINT for cleanup when the script is aborted
  def end_read(self,signal,frame):
      self.forever = 0
      self.logger.warning("Abort detected; stopping")
      self.err = 0

  def on_exit(self,e):
      self.client.disconnect()
      self.logger.info("Closed down.")
      return(e)

  def connect(self):
   try:
      self.client = mqtt.Client()
      self.client.connect(self.cnf.mqtthost)
      self.client.on_message = self.on_message
      self.client.on_connect = self.on_connect
      self.client.on_subscribe= self.on_subscribe
   except:
      self.logger.critical("MQTT connection setup to '"+self.cnf.mqtthost+"' failed:")
      if self.cnf.verbose> 1 :
        raise

      sys.exit(1)

   self.logger.debug("Setting up the connection to '"+self.cnf.mqtthost+"'")

  def loop(self):
    # We should consider using PAHO its 'External event loop support'
    # so we can sit idle when nothing is happening with a bit more ease.
    # As currently our (low) timeout is just there to be responsive to
    # things like card swipes. While in fact for most use cases we can
    # make the sit-tight 'endless'.
    self.client.loop(timeout=self.looptimeout)

  def initialize(self):
    self.parseArguments()
    self.setup()
    self.connect()

  def run(self):
    self.initialize()

    self.forever = 1

    if self.cnf.daemonize:
        daemon.daemonize(self.cnf.pidfile)

    self.logger.warning("Node {} started.".format(self.cnf.node))
    while(self.forever): 
      self.loop()

    self.logger.debug("Aborting loop.")
    e = self.on_exit(None)

    return e 
