// LED data 선 정체 확인용 (아두이노 우노/나노, 5V)
//
// [1단계: 측정] data 선 --[10k]--+--[4.7k]-- GND      (분배비 0.32, 15V 까지 안전)
//                                |
//                                A0
//   아두이노 GND 를 LED/보드의 - 선과 연결한다. LED 는 보드에 꽂힌 그대로 둔다.
//   시리얼 모니터(115200)에 0.5초마다 data 선의 최소/평균/최대 전압이 찍힌다.
//   라이트를 켰다 껐다 해보고 값을 본다.
//     - 최소≈최대, 0V <-> 3~5V   : 논리 신호
//     - 최소≈최대, 0V <-> 11~14V : 12V 전원 스위칭 선 (MCU 로 직접 구동 불가)
//     - 최소와 최대가 크게 다름   : PWM/서보 펄스 (평균이 듀티를 나타냄)
//
// [2단계: 구동] 1단계에서 "논리 신호" 또는 "PWM" 으로 나왔을 때만.
//   data 선을 보드에서 뽑고 D9 --[1k]-- data 에 연결. LED + 는 12V, - 는 GND(아두이노와 공통).
//   시리얼 모니터에 한 글자 입력:
//     1 = HIGH(5V)   0 = LOW   s = 서보 2000us   m = 서보 1500us   n = 서보 1000us
//     p = 50% PWM(490Hz)        r = 1단계 측정으로 돌아감

#include <Servo.h>

const float DIVIDER = 4.7 / (10.0 + 4.7);  // A0 에 보이는 비율
const int PROBE_PIN = A0;
const int DRIVE_PIN = 9;

Servo servo;
char mode = 'r';

void stopDrive() {
  if (servo.attached()) servo.detach();
  pinMode(DRIVE_PIN, INPUT);  // 구동 끄기 = 하이 임피던스
}

void setup() {
  Serial.begin(115200);
  stopDrive();
  Serial.println(F("led_probe: r=측정 1/0=HIGH/LOW s/m/n=서보 2000/1500/1000us p=PWM50%"));
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') return;
    stopDrive();
    mode = c;
    switch (c) {
      case '1': pinMode(DRIVE_PIN, OUTPUT); digitalWrite(DRIVE_PIN, HIGH); break;
      case '0': pinMode(DRIVE_PIN, OUTPUT); digitalWrite(DRIVE_PIN, LOW); break;
      case 's': servo.attach(DRIVE_PIN); servo.writeMicroseconds(2000); break;
      case 'm': servo.attach(DRIVE_PIN); servo.writeMicroseconds(1500); break;
      case 'n': servo.attach(DRIVE_PIN); servo.writeMicroseconds(1000); break;
      case 'p': pinMode(DRIVE_PIN, OUTPUT); analogWrite(DRIVE_PIN, 128); break;
      case 'r': break;
      default: Serial.println(F("모르는 명령")); mode = 'r'; return;
    }
    Serial.print(F("모드: ")); Serial.println(mode);
  }

  if (mode == 'r') {
    // 0.5초 동안 빠르게 샘플링해서 최소/평균/최대 — DC 인지 펄스인지 구분
    int lo = 1023, hi = 0; long sum = 0; int n = 0;
    unsigned long t = millis();
    while (millis() - t < 500) {
      int v = analogRead(PROBE_PIN);
      if (v < lo) lo = v;
      if (v > hi) hi = v;
      sum += v; n++;
    }
    float k = 5.0 / 1023.0 / DIVIDER;
    Serial.print(F("data  min ")); Serial.print(lo * k, 2);
    Serial.print(F("V  avg ")); Serial.print((float)sum / n * k, 2);
    Serial.print(F("V  max ")); Serial.print(hi * k, 2);
    Serial.println(F("V"));
    if (hi * k > 15.0) Serial.println(F("!! 15V 초과 — 즉시 분리"));
  }
}
