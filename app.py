from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>أهلاً وسهلاً</title>
        <style>
            body {
                margin: 0;
                font-family: 'Segoe UI', Tahoma, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                color: white;
            }
            .card {
                background: rgba(255,255,255,0.15);
                backdrop-filter: blur(10px);
                padding: 50px 70px;
                border-radius: 20px;
                text-align: center;
                box-shadow: 0 8px 32px rgba(0,0,0,0.2);
                border: 1px solid rgba(255,255,255,0.18);
            }
            h1 { font-size: 50px; margin: 0; }
            p { font-size: 20px; margin-top: 15px; opacity: 0.9; }
            .btn {
                display: inline-block;
                margin-top: 25px;
                padding: 12px 30px;
                background: white;
                color: #764ba2;
                border-radius: 30px;
                text-decoration: none;
                font-weight: bold;
                transition: 0.3s;
            }
            .btn:hover { transform: scale(1.05); }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>أهلاً وسهلاً 👋</h1>
            <p>السيرفر مالك على Fly.io شغال بنجاح!</p>
            <p>تم النشر من النجف ✨</p>
            <a class="btn" href="#">ابدأ الآن</a>
        </div>
    </body>
    </html>
    """

if __name__ == '__main__':
    # fly.io يستخدم المنفذ 8080
    app.run(host='0.0.0.0', port=8080)
