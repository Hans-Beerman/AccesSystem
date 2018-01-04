#include <ACNode.h>
#include <OTA.h>

OTA::OTA(const char * password) : _ota_password(password) {};

void OTA::begin() {
  ArduinoOTA.setPort(8266);
  ArduinoOTA.setHostname(moi);

  if (_ota_password) 
	  ArduinoOTA.setPassword(_ota_password);
  else 
  	Log.println("**** WARNING -- NO OTA PASSWORD SET *****");

  ArduinoOTA.onStart([]() {
    Log.println("OTA process started.");
    setGreenLED(LED_SLOW);
    setOrangeLED(LED_SLOW);
  });
  ArduinoOTA.onEnd([]() {
    Log.println("OTA process completed. Resetting.");
    setGreenLED(LED_OFF);
    setOrangeLED(LED_ON);
  });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("Progress: %u\n", (progress / (total / 100)));
  });
  ArduinoOTA.onError([](ota_error_t error) {
    setGreenLED(LED_FAST);
    setOrangeLED(LED_FAST);
    Log.printf("Error[%u]: ", error);
    if (error == OTA_AUTH_ERROR) Log.println("OTA: Auth failed");
    else if (error == OTA_BEGIN_ERROR) Log.println("OTA: Begin failed");
    else if (error == OTA_CONNECT_ERROR) Log.println("OTA: Connect failed");
    else if (error == OTA_RECEIVE_ERROR) Log.println("OTA: Receive failed");
    else if (error == OTA_END_ERROR) Log.println("OTA: End failed");
    else {
      Log.print("OTA: Error: ");
      Log.println(error);
    };
  });
  
#ifdef  ESP32
  ArduinoOTA.begin(TCPIP_ADAPTER_IF_ETH);
  Log.println("OTA Enabled on the wired Ethernet interface");
#else
  ArduinoOTA.begin();
  Log.println("OTA Enabled");
#endif
}

void OTA::loop() {
  ArduinoOTA.handle();
}
