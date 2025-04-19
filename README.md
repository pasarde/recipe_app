# Recipe Suggestion App

This is the ML component of the Recipe Suggestion App. It uses spoonacular api to recommend recipes based on user-provided ingredients.

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/desxtra/recipe_suggestions.git
   cd recipe_suggestions
   ```

2. Install dependencies:
    ```bash
    pip install -r requirements.txt
    pip install cohere
    ```

3. Add your Spoonacular and Cohere API key to a .env file:

    - SPOONACULAR_KEY="YOUR_SPOONACULAR_API_KEY"
    - COHERE_KEY="YOUR_COHERE_API_KEY"

4. Run the App:
    ```bash
    python app.py
    ```