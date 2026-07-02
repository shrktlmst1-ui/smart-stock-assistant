# Smart Stock Assistant

مساعد تداول ذكي للمضاربة السريعة — **بيانات حية من Polygon/Massive، تحليل وتنبيهات فقط.**

## التشغيل السريع

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
# ضع مفتاح API في backend/.env
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

افتح: http://localhost:5173

## إعداد API (backend/.env)

```env
MASSIVE_API_KEY=your_key
POLYGON_API_KEY=your_key
POLYGON_PLAN=developer
WEBSOCKET_ENABLED=true
POLL_INTERVAL_SECONDS=1
WATCHLIST=AAPL,NVDA,TSLA,AMD,MSFT,META,AMZN,GOOGL
```

## حالة الاتصال

الواجهة تعرض:
- **API Connected** — اتصال REST
- **Authentication** — مصادقة المفتاح
- **Subscription** — خطة developer
- **Live Market Data** — بيانات حية
- **WebSocket** أو **REST Polling** (كل ثانية كاحتياطي)

## التحليل المدعوم

سيولة، أموال ذكية، تدفق أوامر، قفزة فوليوم، VWAP، RSI، MACD، EMA 9/20/50/200، دعم/مقاومة، اختراق وهمي، مصيدة سيولة، تنبيهات شراء/بيع.

## تحذير

للمتابعة والتحليل فقط — ليست نصيحة استثمارية.
