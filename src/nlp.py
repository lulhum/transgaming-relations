from transformers import pipeline

model_path = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
nlp = pipeline("sentiment-analysis", model=model_path, tokenizer=model_path)

def score(msg):
    data = nlp(msg, top_k=None)
    data = {d['label']: d['score'] for d in data}
    return data['positive'] - data['negative']
