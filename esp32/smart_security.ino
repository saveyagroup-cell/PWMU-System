#define PIR_PIN       27
#define IR_PIN        26
#define FLAME_PIN     25
#define MQ5_PIN       34
#define BUZZER_PIN    23

int GAS_THRESHOLD = 1800;
unsigned long lastSend = 0;

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  pinMode(IR_PIN, INPUT);
  pinMode(FLAME_PIN, INPUT);
  pinMode(MQ5_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  // Prototype warm-up. MQ-5 needs proper calibration for real deployment.
  delay(30000);
}

void loop() {
  int pir = digitalRead(PIR_PIN);
  int doorSensor = digitalRead(IR_PIN);

  // Many flame sensor modules use active-LOW DO.
  bool fire = digitalRead(FLAME_PIN) == LOW;

  int gasValue = analogRead(MQ5_PIN);
  bool gas = gasValue > GAS_THRESHOLD;

  if (millis() - lastSend >= 250) {
    Serial.print("PIR:"); Serial.print(pir);
    Serial.print(",IR:"); Serial.print(doorSensor);
    Serial.print(",FIRE:"); Serial.print(fire ? 1 : 0);
    Serial.print(",GAS:"); Serial.print(gas ? 1 : 0);
    Serial.print(",GAS_VALUE:"); Serial.println(gasValue);
    lastSend = millis();
  }

  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();

    if (command == "BUZZER_ON") digitalWrite(BUZZER_PIN, HIGH);
    else if (command == "BUZZER_OFF") digitalWrite(BUZZER_PIN, LOW);
  }
}
