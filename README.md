# 🍳 Recipeze - Recipe Suggestion App

A smart recipe recommendation application that suggests recipes based on ingredients, weather conditions, and user preferences. Built with Flask, SQLAlchemy, and integrates with multiple recipe APIs.

## ✨ Features

- 🔍 Smart recipe recommendations
- 🌤️ Weather-based recipe suggestions
- 👥 User authentication system
- 💬 Real-time community chat
- 📱 Responsive design
- 🔒 Secure file uploads
- ❤️ Recipe interaction system (like/save)
- 💾 User recipe submission
- 🔍 Advanced search capabilities

## 🛠️ Tech Stack

- **Backend**: Python, Flask
- **Database**: SQLAlchemy, SQLite
- **Frontend**: HTML, CSS, Bootstrap 5
- **APIs**: 
  - Spoonacular (Recipe data)
  - OpenWeather (Weather data)
  - Cohere (ML recommendations)
- **Real-time**: Socket.IO
- **Security**: Flask-Login, CSRFProtect

## 📋 Prerequisites

- Python 3.8+
- pip package manager
- Git

## 🚀 Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/recipe_suggestions.git
cd recipe_suggestions
```

2. Create and activate virtual environment:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Unix/MacOS
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create .env file with your API keys:
```env
SPOONACULAR_KEY="your_spoonacular_api_key"
COHERE_KEY="your_cohere_api_key"
OPENWEATHER_KEY="your_openweather_api_key"
SECRET_KEY="your_secret_key"
DATABASE_URL="sqlite:///database.db"
```

5. Initialize the database:
```bash
flask db upgrade
```

6. Run the application:
```bash
python app.py
```

Visit `http://localhost:5000` in your browser.

## 📁 Project Structure

```
recipe_suggestions/
├── static/
│   ├── css/
│   ├── js/
│   └── uploads/
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   └── ...
├── app.py
├── models.py
├── requirements.txt
└── README.md
```

## 🔒 Security Features

- Password hashing
- CSRF protection
- Input sanitization
- File upload validation
- Rate limiting
- Session management

## 💬 Chat Features

- Real-time messaging
- 24-hour message cleanup
- Anti-spam protection
- User authentication required

## 👤 User Features

- Profile management
- Recipe submissions
- Recipe interactions
- Comment system
- Search history

## 🌟 API Integration

### Spoonacular API
- Recipe search
- Recipe details
- Ingredient-based suggestions

### OpenWeather API
- Current weather data
- Location-based suggestions

### Cohere API
- ML-powered recommendations
- Natural language processing

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👏 Acknowledgments

- [Spoonacular API](https://spoonacular.com/food-api)
- [OpenWeather API](https://openweathermap.org/api)
- [Cohere API](https://cohere.ai/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Bootstrap](https://getbootstrap.com/)

## 📧 Contact

Your Name - [@yourusername](https://twitter.com/yourusername)

Project Link: [https://github.com/yourusername/recipe_suggestions](https://github.com/yourusername/recipe_suggestions)