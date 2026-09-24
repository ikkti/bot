# خادم البث الصوتي المباشر فائق السرعة (Real-Time Audio Broadcast)

خادم مصمم للبث الصوتي الفوري بدون تأخير (Low Latency) ومستعد للنشر المباشر على سحابة **Fly.io**، مع دعم كامل لواجهات **REST API** و **WebSocket** للربط مع تطبيقات الهواتف الذكية (Flutter, React Native, iOS, Android).

---

## 🌟 المميزات
1. **بث فوري بدون تأخير (Zero/Low-latency):** بث البيانات الصوتية بتدفق خام عبر WebSockets.
2. **واجهات برمجية REST API:**
   - معرفة حالة البث وعدد المستمعين في اللحظة الفعلية.
   - تحديث عنوان البث والبيانات الوصفية.
   - إيقاف البث عن بعد برمجياً عبر الـ API.
3. **أمان عالي (API Key Authentication):** حماية واجهات التحكم وحماية قناة البث لضمان عدم قيام أي شخص غريب بالبث.
4. **واجهة ويب تجريبية مدمجة:** تتيح لك اختبار البث من الميكروفون والاستماع مباشرة من المتصفح.
5. **جاهز لـ Fly.io:** يتضمن ملفات `Dockerfile` و `fly.toml` لإطلاق الخادم بأمر واحد.

---

## 🚀 كيفية النشر على Fly.io

1. **تثبيت أداة Fly CLI وتسجيل الدخول:**
   ```bash
   fly auth login
   ```
2. **إطلاق التطبيق:**
   قم بتشغيل الأمر التالي داخل مجلد المشروع:
   ```bash
   fly launch --no-deploy
   ```
   (اختر اسماً لتطبيقك وحدد أقرب منطقة جغرافية للمستخدمين).

3. **تعيين مفاتيح الأمان في سحابة Fly:**
   ```bash
   fly secrets set API_KEY="your-strong-production-api-key"
   ```

4. **رفع ونشر المشروع:**
   ```bash
   fly deploy
   ```

سيعمل الخادم مباشرة على الرابط: `https://your-app-name.fly.dev`

---

## 📡 توثيق الـ APIs (للربط مع تطبيقك)

### 1. الاستعلام عن حالة البث (عام - بدون صلاحيات)
- **Endpoint:** `GET /api/status`
- **Response:**
  ```json
  {
    "success": true,
    "data": {
      "isLive": true,
      "title": "حلقة بودكاست مباشرة",
      "startedAt": "2026-09-24T15:30:00.000Z",
      "totalListeners": 42,
      "peakListeners": 65
    }
  }
  ```

---

### 2. تحديث بيانات البث (محمي بـ API Key)
- **Endpoint:** `POST /api/stream/meta`
- **Headers:** `Authorization: Bearer <API_KEY>` أو `Content-Type: application/json`
- **Body:**
  ```json
  {
    "title": "محادثة صوتية جديدة"
  }
  ```

---

### 3. إيقاف البث إجبارياً عن بُعد (محمي بـ API Key)
- **Endpoint:** `POST /api/stream/stop`
- **Headers:** `Authorization: Bearer <API_KEY>`

---

## 🎙️ ربط البث والاستماع في تطبيق الموبايل (WebSocket)

### 🔴 كـ مُذيع (Broadcaster):
افتح اتصال WebSocket إلى:
```
wss://your-app-name.fly.dev?role=broadcaster&apiKey=YOUR_API_KEY
```
ثم أرسل عينات الصوت المسجلة من الميكروفون (PCM 16-bit أو Opus) كحزم ثنائية (Binary Buffer).

### 🟢 كـ مُستمع (Listener):
افتح اتصال WebSocket إلى:
```
wss://your-app-name.fly.dev?role=listener
```
بمجرد الاتصال، سيقوم الخادم بضخ حزم الصوت الثنائية الواردة من المذيع لتشغيلها مباشرة في تطبيقك فوراً بدون تأخير!
