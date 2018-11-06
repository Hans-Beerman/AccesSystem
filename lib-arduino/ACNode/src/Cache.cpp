#include <Cache.h>
#include <string.h>
#include <Arduino.h>
#include "FS.h"
#include "SPIFFS.h"

#define CACHE_DIR_PREFIX "/uid-"

static String uid2path(const char * tag) {
  String path = CACHE_DIR_PREFIX;
 
  byte crc = 0;
  for(const char * p = tag; p && *p; p++)
	crc = (( 37 * crc ) + *p) & 0xFF;

  return CACHE_DIR_PREFIX + String(crc,HEX) + "/" + tag;
}

void prepareCache(bool wipe) {
  Serial.println("Formatted.");
  if (!SPIFFS.begin()) {
    Serial.println("SPIFFS mount after formatting failed.");
    return;
  };

  for (int i = 0; i < 255; i++) {
    String dirName = CACHE_DIR_PREFIX + String(i,HEX);
    SPIFFS.mkdir(dirName);
	
    if (!wipe)
	continue;

    File dir = SPIFFS.open(dirName);
    File file = dir.openNextFile();
    while(file) {
	String path = dirName + "/" + file.name();

	file.close();
        SPIFFS.remove(path);

	file = file.openNextFile();
    };
    dir.close();
  };
};

void setCache(const char * tag, bool ok, unsigned long beatCounter) {
  String path = uid2path(tag) + ".lastOK";
  if (ok) {
    File f = SPIFFS.open(path, "w");
    f.println(beatCounter);
    f.close();
  } else {
    SPIFFS.remove(path);
  }
};

bool checkCache(const char * tag) {
  String path = uid2path(tag) + ".lastOK";
  return SPIFFS.exists(path);
};
