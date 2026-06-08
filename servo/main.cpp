#include <Arduino.h>
#include <Servo.h>
#include <stdlib.h>
#include <string.h>

// Protocol from Python:
//   S0,S1,S2,S3,S4,S5\n
// Example:
//   180,90,135,75,90,40\n
//
// Keep this file focused on hardware control. The PC/server decides target
// angles; Arduino validates ranges and emits servo pulses.

struct JointConfig {
  const char *name;
  byte pin;
  int minAngle;
  int maxAngle;
  int homeAngle;
  int pulseMin;
  int pulseMax;
};

const byte JOINT_COUNT = 6;

JointConfig joints[JOINT_COUNT] = {
    {"S0_BASE", 3, 0, 360, 180, 500, 2500},
    {"S1_SHOULDER", 5, 0, 180, 90, 500, 2500},
    {"S2_ELBOW", 6, 0, 270, 135, 500, 2500},
    {"S3_WRIST_PITCH", 9, 0, 150, 75, 500, 2500},
    {"S4_WRIST_ROLL", 10, 0, 180, 90, 500, 2500},
    {"S5_GRIPPER", 11, 25, 70, 40, 500, 2500},
};

Servo servos[JOINT_COUNT];
int currentAngles[JOINT_COUNT];

char input[48];
byte inputIndex = 0;

int logicalAngleToPulse(const JointConfig &joint, int angle) {
  angle = constrain(angle, joint.minAngle, joint.maxAngle);
  return map(angle, joint.minAngle, joint.maxAngle, joint.pulseMin, joint.pulseMax);
}

void writeJoint(byte index, int angle) {
  currentAngles[index] = constrain(angle, joints[index].minAngle, joints[index].maxAngle);
  servos[index].writeMicroseconds(logicalAngleToPulse(joints[index], currentAngles[index]));
}

bool parseAngles(char *line, int angles[JOINT_COUNT]) {
  char *cursor = line;

  for (byte i = 0; i < JOINT_COUNT; i++) {
    char *end = strchr(cursor, ',');

    if (i < JOINT_COUNT - 1) {
      if (end == NULL) {
        return false;
      }
      *end = '\0';
    } else if (end != NULL) {
      return false;
    }

    if (*cursor == '\0') {
      return false;
    }

    int angle = atoi(cursor);
    if (angle < joints[i].minAngle || angle > joints[i].maxAngle) {
      return false;
    }

    angles[i] = angle;

    if (end != NULL) {
      cursor = end + 1;
    }
  }

  return true;
}

void handleLine() {
  input[inputIndex] = '\0';

  int angles[JOINT_COUNT];
  if (parseAngles(input, angles)) {
    for (byte i = 0; i < JOINT_COUNT; i++) {
      writeJoint(i, angles[i]);
    }
  }

  inputIndex = 0;
}

void setup() {
  Serial.begin(9600);

  for (byte i = 0; i < JOINT_COUNT; i++) {
    servos[i].attach(joints[i].pin);
    writeJoint(i, joints[i].homeAngle);
  }
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n') {
      handleLine();
    } else if ((c >= '0' && c <= '9') || c == ',') {
      if (inputIndex < sizeof(input) - 1) {
        input[inputIndex++] = c;
      } else {
        inputIndex = 0;
      }
    } else if (c != '\r') {
      inputIndex = 0;
    }
  }
}
