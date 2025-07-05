import pickle
from flask import Flask, request, render_template
import numpy as np

# Initialize Flask app
application = Flask(__name__)
app1 = application

# Load model and scaler
ridge1_model = pickle.load(open('models/ridge1.pkl', 'rb'))
standard_scaler = pickle.load(open('models/scaler1.pkl', 'rb'))

@app1.route('/')
def home():
    return render_template('home1.html')

@app1.route('/predictdatapoint', methods=['GET', 'POST'])
def predict_datapoint():
    if request.method == "POST":
        try:
            area = float(request.form.get('area'))
            bedrooms = float(request.form.get('bedrooms'))
            bathrooms = float(request.form.get('bathrooms'))
            stories = float(request.form.get('stories'))
            mainroad = float(request.form.get('mainroad'))
            basement = float(request.form.get('basement'))
            parking = float(request.form.get('parking'))

            features = [[area, bedrooms, bathrooms, stories, mainroad, basement, parking]]
            new_data_scaled = standard_scaler.transform(features)
            result = ridge1_model.predict(new_data_scaled)

            return render_template('home1.html', result=result[0])
        except Exception as e:
            return f"Error: {e}"
    else:
        return render_template('home1.html')

if __name__ == "__main__":
    app1.run(debug=True, host="0.0.0.0")
