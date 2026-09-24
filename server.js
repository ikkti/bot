require('dotenv').config();
const http = require('http');
const express = require('express');
const { WebSocketServer, WebSocket } = require('ws');
const path = require('path');
const cors = require('cors');

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const PORT = process.env.PORT || 8080;
const API_KEY = process.env.API_KEY || 'my-super-secret-api-key-2026';

// حالة البث المباشر وقائمة المتصلين
const streamState = {
  isLive: false,
  title: 'البث المباشر الافتراضي',
  startedAt: null,
  broadcasterId: null,
  totalListeners: 0,
  peakListeners: 0
};

// خريطة المستمعين المتصلين
const listeners = new Set();
let broadcasterSocket = null;

// Middleware لحماية الـ REST APIs
function authenticateApiKey(req, res, next) {
  const authHeader = req.headers['authorization'];
  const queryKey = req.query.apiKey;
  const token = authHeader ? authHeader.replace(/^Bearer\s+/i, '') : queryKey;

  if (!token || token !== API_KEY) {
    return res.status(401).json({
      success: false,
      error: 'مفتاح API غير صالح أو غير موجود (Unauthorized)'
    });
  }
  next();
}

// ---------------- REST APIs للتطبيق الخارجي ---------------- //

// فحص صحة الخادم
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    uptime: process.uptime(),
    timestamp: new Date().toISOString()
  });
});

// جلب حالة البث الحالية وعدد المستمعين
app.get('/api/status', (req, res) => {
  res.json({
    success: true,
    data: {
      ...streamState,
      totalListeners: listeners.size
    }
  });
});

// تعديل بيانات البث (محمي بـ API Key)
app.post('/api/stream/meta', authenticateApiKey, (req, res) => {
  const { title } = req.body;
  if (title) {
    streamState.title = title;
  }
  res.json({
    success: true,
    message: 'تم تحديث بيانات البث بنجاح',
    data: streamState
  });
});

// إنهاء البث إجبارياً من الـ API (محمي بـ API Key)
app.post('/api/stream/stop', authenticateApiKey, (req, res) => {
  if (broadcasterSocket && broadcasterSocket.readyState === WebSocket.OPEN) {
    broadcasterSocket.close(1000, 'Stopped by API request');
  }
  streamState.isLive = false;
  streamState.startedAt = null;
  res.json({
    success: true,
    message: 'تم إيقاف البث بنجاح'
  });
});

// ---------------- إنشاء خادم الـ HTTP و WebSocket ---------------- //

const server = http.createServer(app);
const wss = new WebSocketServer({ server });

wss.on('connection', (ws, req) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const role = url.searchParams.get('role'); // 'broadcaster' أو 'listener'
  const clientKey = url.searchParams.get('apiKey');

  if (role === 'broadcaster') {
    // التحقق من الصلاحية للبث
    if (clientKey !== API_KEY) {
      ws.close(4001, 'Unauthorized: Invalid API Key');
      return;
    }

    if (broadcasterSocket && broadcasterSocket.readyState === WebSocket.OPEN) {
      ws.close(4002, 'Broadcaster already connected');
      return;
    }

    broadcasterSocket = ws;
    streamState.isLive = true;
    streamState.startedAt = new Date().toISOString();
    console.log('[BROADCASTER] Connected');

    // إشعار جميع المستمعين ببدء البث
    broadcastStatusToAll();

    ws.on('message', (data, isBinary) => {
      // إذا كانت حزمة صوتية خام (Binary Audio Buffer) نقوم بتمريرها فورياً بدون تأخير لجميع المستمعين
      if (isBinary) {
        for (const listener of listeners) {
          if (listener.readyState === WebSocket.OPEN) {
            listener.send(data, { binary: true });
          }
        }
      } else {
        try {
          const parsed = JSON.parse(data.toString());
          if (parsed.type === 'meta_update' && parsed.title) {
            streamState.title = parsed.title;
            broadcastStatusToAll();
          }
        } catch (e) {}
      }
    });

    ws.on('close', () => {
      console.log('[BROADCASTER] Disconnected');
      broadcasterSocket = null;
      streamState.isLive = false;
      broadcastStatusToAll();
    });

  } else {
    // دور المستمع (Listener)
    listeners.add(ws);
    streamState.totalListeners = listeners.size;
    if (listeners.size > streamState.peakListeners) {
      streamState.peakListeners = listeners.size;
    }
    console.log(`[LISTENER] Connected. Total: ${listeners.size}`);

    // إرسال الحالة الحالية للمستمع
    ws.send(JSON.stringify({
      type: 'status',
      data: {
        isLive: streamState.isLive,
        title: streamState.title,
        listeners: listeners.size
      }
    }));

    ws.on('close', () => {
      listeners.delete(ws);
      streamState.totalListeners = listeners.size;
      console.log(`[LISTENER] Disconnected. Total: ${listeners.size}`);
    });
  }
});

function broadcastStatusToAll() {
  const msg = JSON.stringify({
    type: 'status',
    data: {
      isLive: streamState.isLive,
      title: streamState.title,
      listeners: listeners.size
    }
  });

  for (const listener of listeners) {
    if (listener.readyState === WebSocket.OPEN) {
      listener.send(msg);
    }
  }
}

server.listen(PORT, () => {
  console.log(`===============================================`);
  console.log(` Live Audio Broadcast Server running on port ${PORT}`);
  console.log(` API Endpoint: http://localhost:${PORT}/api/status`);
  console.log(` WebSocket:    ws://localhost:${PORT}`);
  console.log(`===============================================`);
});
