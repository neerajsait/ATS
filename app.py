import PyPDF2
import docx
import spacy
import nltk
from nltk.corpus import wordnet
import pdfplumber
import pytesseract
from PIL import Image
import re
import os
from flask import Flask, request, render_template
from textstat import flesch_reading_ease
from transformers import BertTokenizer, BertModel
import torch
import random
import requests
from bs4 import BeautifulSoup
from gensim.models import FastText
import numpy as np 
import faiss
from sklearn.ensemble import RandomForestRegressor
import conceptnet_lite
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize models and Flask
nlp = spacy.load("en_core_web_sm")
tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
bert_model = BertModel.from_pretrained('bert-base-uncased')
nltk.download('wordnet')
app = Flask(__name__)

nlp_fr = spacy.load("fr_core_news_sm") if spacy.util.is_package("fr_core_news_sm") else None

# Extended keyword clusters and industry skills
keyword_clusters = {
    'python': ['numpy', 'pandas', 'sklearn', 'tensorflow'],
    'java': ['spring', 'hibernate', 'maven'],
    'coding': ['programming', 'development', 'software'],
    'teamwork': ['collaboration', 'group', 'cooperation'],
    'communication': ['presentation', 'writing', 'verbal']
}

industry_skills = {
    'Tech': {'python', 'java', 'sql', 'aws', 'docker'},
    'Finance': {'excel', 'accounting', 'risk', 'finance', 'audit'},
    'Healthcare': {'nursing', 'emr', 'patient', 'clinical', 'hipaa'}
}

top_resumes = {
    'Tech': "python java sql aws docker 5 years experience",
    'Finance': "excel accounting risk management 3 years experience",
    'Healthcare': "nursing patient care emr 4 years experience"
}

# ATS-specific rules with validation confidence
ats_dialects = {
    'Taleo': {
        'max_sentence_length': 20,
        'dislikes_headers': False,
        'prefers_keywords': True,
        'confidence': 0.9,
        'validation_source': 'Industry reports (Ongig, Jobscan)'
    },
    'Workday': {
        'max_sentence_length': 15,
        'dislikes_headers': True,
        'prefers_keywords': False,
        'confidence': 0.85,
        'validation_source': 'User feedback (G2, Reddit)'
    },
    'Greenhouse': {
        'max_sentence_length': 25,
        'dislikes_headers': False,
        'prefers_keywords': True,
        'confidence': 0.9,
        'validation_source': 'ATS documentation'
    },
    'iCIMS': {
        'max_sentence_length': 20,
        'dislikes_headers': False,
        'prefers_keywords': True,
        'dislikes_complex_formatting': True,
        'confidence': 0.8,
        'validation_source': 'JobTestPrep, G2 reviews'
    },
    'BrassRing': {
        'max_sentence_length': 22,
        'dislikes_headers': True,
        'prefers_keywords': True,
        'dislikes_hyperlinks': True,
        'confidence': 0.8,
        'validation_source': 'JobTestPrep, BrassRing documentation'
    },
    'Generic': {
        'max_sentence_length': 25,
        'dislikes_headers': False,
        'prefers_keywords': True,
        'confidence': 0.7,
        'validation_source': 'Assumed baseline'
    }
}

tracked_jobs = []

ft_model = FastText(sentences=[["python", "java", "sql", "teamwork"]], vector_size=100, window=5, min_count=1)
dimension = 100
faiss_index = faiss.IndexFlatL2(dimension)

hiring_trends = [
    ([5, 3, 2, 1], 0.9),
    ([2, 2, 1, 0], 0.6),
    ([1, 1, 0, 0], 0.3)
]
X_train = [x[0] for x in hiring_trends]
y_train = [x[1] for x in hiring_trends]
rf_model = RandomForestRegressor(n_estimators=10).fit(X_train, y_train)

def extract_text(file_path):
    logger.debug(f"Extracting text from {file_path}")
    if file_path.endswith('.pdf'):
        with pdfplumber.open(file_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or pytesseract.image_to_string(page.to_image().original)
                text += page_text + "\n"
            return text.lower(), 'en' if 'skills' in text.lower() else 'fr'
    elif file_path.endswith('.docx'):
        doc = docx.Document(file_path)
        text = " ".join([para.text for para in doc.paragraphs]).lower()
        return text, 'en' if 'skills' in text.lower() else 'fr'
    return "Unsupported file type.", 'en'

def clean_text(text):
    return re.sub(r'[^\w\s\-\•\*\.]', '', text)

def detect_sections(resume_text, lang='en'):
    logger.debug(f"Detecting sections for resume_text: {resume_text[:50]}...")
    nlp_model = nlp if lang == 'en' or nlp_fr is None else nlp_fr
    doc = nlp_model(resume_text)
    sections = {'skills': {'hard': [], 'soft': []}, 'experience': [], 'education': []}
    current_section = None
    hard_skills = industry_skills.get('Tech', set())
    soft_skills = {'teamwork', 'communication', 'leadership', 'problem-solving'}

    for sent in doc.sents:
        text = sent.text.lower().strip()
        if any(k in text for k in ['skills', 'skill', 'technical']):
            current_section = 'skills'
        elif any(k in text for k in ['experience', 'internship', 'work', 'job']) or any(ent.label_ == 'ORG' for ent in sent.ents):
            current_section = 'experience'
        elif any(k in text for k in ['education', 'university', 'degree', 'gpa']) or any(ent.label_ == 'GPE' for ent in sent.ents):
            current_section = 'education'
        elif current_section:
            cleaned = text[1:].strip() if text.startswith(('•', '*', '-')) else text
            if current_section == 'skills':
                words = set(cleaned.split())
                sections['skills']['hard'].extend([w for w in words if w in hard_skills])
                sections['skills']['soft'].extend([w for w in words if w in soft_skills])
            else:
                sections[current_section].append(cleaned)
    return sections

def get_bert_embedding(text):
    inputs = tokenizer(text, return_tensors='pt', truncation=True, padding=True, max_length=512)
    with torch.no_grad():
        outputs = bert_model(**inputs)
    return outputs.last_hidden_state.mean(dim=1).squeeze().numpy()

def expand_keywords(job_keywords):
    expanded = set(job_keywords)
    for keyword in job_keywords:
        if keyword in keyword_clusters:
            expanded.update(keyword_clusters[keyword])
        try:
            for link in conceptnet_lite.concepts[f'/{keyword}/en'].edges_out:
                if link.relation.name in ['IsA', 'RelatedTo']:
                    expanded.add(link.end.name.split('/')[-1].lower())
        except:
            pass
    return expanded

def calculate_ats_score(resume_text, job_description, lang='en', ats_system='Generic'):
    logger.debug(f"Calculating ATS score for resume_text: {resume_text[:50]}... ATS: {ats_system}")
    resume_text = clean_text(resume_text)
    job_description = clean_text(job_description)
    nlp_model = nlp if lang == 'en' or nlp_fr is None else nlp_fr
    resume_doc = nlp_model(resume_text)
    job_doc = nlp_model(job_description)

    job_keywords = set(token.text for token in job_doc if token.pos_ in ['NOUN', 'VERB'] and not token.is_stop)
    expanded_keywords = expand_keywords(job_keywords)
    total_keywords = len(expanded_keywords)

    sections = detect_sections(resume_text, lang)
    job_vec = ft_model.wv[job_description.split()]
    resume_vec = ft_model.wv[resume_text.split()]
    job_embedding = get_bert_embedding(job_description)

    weights = {'skills': 0.5, 'experience': 0.3, 'education': 0.2}
    matches = {'skills': {'hard': [], 'soft': []}, 'experience': [], 'education': []}
    section_scores = {}
    score = 0

    faiss_index.add(np.mean(job_vec, axis=0).reshape(1, -1))
    D, _ = faiss_index.search(np.mean(resume_vec, axis=0).reshape(1, -1), 1)
    faiss_similarity = 1 - D[0][0] / 100

    for section, weight in weights.items():
        section_text = ' '.join(sections[section]['hard'] + sections[section]['soft'] if section == 'skills' else sections[section])
        if section_text:
            section_embedding = get_bert_embedding(section_text)
            similarity = torch.cosine_similarity(
                torch.tensor(job_embedding).unsqueeze(0),
                torch.tensor(section_embedding).unsqueeze(0)
            ).item()
            section_matches = [token.text for token in nlp(section_text) if token.text in expanded_keywords]
            if section == 'skills':
                matches[section]['hard'] = [m for m in section_matches if m in industry_skills.get('Tech', set())]
                matches[section]['soft'] = [m for m in section_matches if m in {'teamwork', 'communication'}]
            else:
                matches[section] = list(set(section_matches))
            section_score = (len(matches[section]['hard'] + matches[section]['soft'] if section == 'skills' else matches[section]) / total_keywords + similarity) * 50 * weight
            score += section_score
            section_scores[section] = section_score

    if any(t in resume_text for t in {'internship', 'project', 'gpa'}):
        score = min(100, score + 10)
    word_count = len(resume_text.split())
    vcs = min(100, 100 - abs(word_count - 200) * 0.2)
    readability = max(0, min(100, flesch_reading_ease(resume_text)))
    score = (score * 0.7) + (vcs * 0.15) + (readability * 0.1 / 100) + (faiss_similarity * 5)

    all_matches = set(sum([matches[s]['hard'] + matches[s]['soft'] if s == 'skills' else matches[s] for s in matches], []))
    missing_keywords = expanded_keywords - all_matches
    missing_entities = {'ORG': 'company'} if 'ORG' not in {ent.label_: ent.text for ent in resume_doc.ents} else {}

    return score, matches, missing_keywords, vcs, readability, missing_entities, section_scores

def check_formatting_and_dialect(resume_text, job_description, ats_system='Generic'):
    feedback = f"Detected ATS: {ats_system}\n"
    ats_rules = ats_dialects.get(ats_system, ats_dialects['Generic'])
    feedback += f"Rule Confidence: {ats_rules['confidence']*100:.0f}% (Source: {ats_rules['validation_source']})\n"
    
    word_count = len(resume_text.split())
    if word_count < 150:
        feedback += "Warning: Resume too short (<1 page).\n"
    elif word_count > 400:
        feedback += "Warning: Resume too long (>2 pages).\n"
    
    sentences = resume_text.split('.')
    avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0
    if avg_sentence_length > ats_rules['max_sentence_length']:
        feedback += f"Caution: Average sentence length ({avg_sentence_length:.1f} words) exceeds {ats_system} limit ({ats_rules['max_sentence_length']} words).\n"
    
    if ats_rules['dislikes_headers'] and re.search(r'^\s*(skills|experience|education)\s*$', resume_text, re.MULTILINE):
        feedback += "Caution: Headers detected, not preferred by this ATS.\n"
    
    if '|' in resume_text or '#' in resume_text:
        feedback += "Caution: Special characters detected.\n"
    if re.search(r'\[.*?\]', resume_text):
        feedback += "Caution: Possible table detected.\n"
    
    # iCIMS-specific checks
    if ats_system == 'iCIMS' and ats_rules.get('dislikes_complex_formatting'):
        if re.search(r'[^\•\-\*]', resume_text):  # Non-standard bullets
            feedback += "Caution: iCIMS prefers standard bullet styles (•, -, *).\n"
    
    # BrassRing-specific checks
    if ats_system == 'BrassRing' and ats_rules.get('dislikes_hyperlinks'):
        if re.search(r'\b(http|mailto|tel):', resume_text, re.IGNORECASE):
            feedback += "Caution: BrassRing may not parse hyperlinks correctly.\n"
        if re.search(r'[^\•]', resume_text):  # Non-standard bullets
            feedback += "Caution: BrassRing prefers standard round bullets (•).\n"
    
    return feedback, ats_system

def predict_success(resume_text, score):
    logger.debug(f"Predicting success for resume_text: {resume_text[:50]}...")
    years_exp = len(re.findall(r'\d+ year', resume_text))
    skills_matched = len(set(resume_text.split()) & industry_skills.get('Tech', set()))
    soft_skills = len(set(resume_text.split()) & {'teamwork', 'communication'})
    projects = len(re.findall(r'project', resume_text))
    features = [years_exp, skills_matched, soft_skills, projects]
    rsp = rf_model.predict([features])[0] * 100
    return min(100, rsp), "High" if rsp > 75 else "Moderate" if rsp > 50 else "Low"

def generate_tailored_suggestions(resume_text, missing_keywords, section_scores):
    suggestions = []
    if 'skills' in section_scores and section_scores['skills'] < 25:
        suggestions.append("Add more relevant hard skills (e.g., " + ', '.join(list(missing_keywords)[:3]) + ") to your Skills section.")
    if 'experience' in section_scores and section_scores['experience'] < 15:
        suggestions.append("Enhance Experience section with measurable results and keywords like " + ', '.join(list(missing_keywords)[:2]) + ".")
    if 'education' in section_scores and section_scores['education'] < 10:
        suggestions.append("Include specific coursework or certifications relevant to the job.")
    return suggestions

def generate_feedback(score, matches, missing_keywords, vcs, readability, missing_entities, formatting_feedback, rsp, rsp_label, section_scores, tailored_suggestions, industry='Tech', resume_text='', ats_system='Generic'):
    logger.debug(f"Generating feedback with resume_text: {resume_text[:50]}...")
    feedback = f"ATS Match Rate: {score:.2f}/100 (Aim for 75+)\nVisual Clarity: {vcs:.2f}/100\nReadability: {readability:.2f}/100\nSuccess Prediction: {rsp:.2f}/100 ({rsp_label})\n"
    feedback += "\nSection-wise Scores:\n" + "\n".join(f"- {s.capitalize()}: {section_scores[s]:.2f}/{(0.5 if s == 'skills' else 0.3 if s == 'experience' else 0.2) * 50}" for s in section_scores)
    feedback += "\nMatches:\n" + "\n".join(f"- {s.capitalize()}: Hard: {', '.join(matches[s]['hard'])}, Soft: {', '.join(matches[s]['soft'])}" if s == 'skills' else f"- {s.capitalize()}: {', '.join(matches[s])}" for s in matches)
    feedback += f"\nSkills Gap (Missing Keywords): {', '.join(list(missing_keywords)[:10])}" + ("..." if len(missing_keywords) > 10 else "")
    feedback += f"\nMissing Entities: {', '.join([f'{k}: {v}' for k, v in missing_entities.items()]) or 'None'}\n"
    feedback += f"\nFormatting & ATS Compatibility:\n{formatting_feedback}"
    feedback += f"\nDialect Validation: Rules for {ats_system} are based on {ats_dialects[ats_system]['validation_source']} with {ats_dialects[ats_system]['confidence']*100:.0f}% confidence.\n"
    feedback += "\nTailored Suggestions:\n" + "\n".join(tailored_suggestions or ["No specific suggestions at this time."])
    return feedback

@app.route('/', methods=['GET', 'POST'])
def index():
    resume_text = ''
    job_description = ''
    feedback = None
    industry = 'Tech'
    ats_system = 'Generic'
    
    logger.debug("Entering index route")
    if request.method == 'POST':
        logger.debug("Processing POST request")
        resume_file = request.files.get('resume')
        job_description = request.form.get('job_description', '')
        industry = request.form.get('industry', 'Tech')
        ats_system = request.form.get('ats_system', 'Generic')
        if not resume_file or not job_description:
            feedback = "Error: Please upload a resume and provide a job description."
            logger.warning("Missing resume file or job description")
        else:
            resume_path = os.path.join('uploads', resume_file.filename)
            resume_file.save(resume_path)
            resume_text, lang = extract_text(resume_path)
            logger.debug(f"Resume text extracted: {resume_text[:50]}...")
            
            try:
                score, matches, missing_keywords, vcs, readability, missing_entities, section_scores = calculate_ats_score(resume_text, job_description, lang, ats_system)
                formatting_feedback, detected_ats = check_formatting_and_dialect(resume_text, job_description, ats_system)
                rsp, rsp_label = predict_success(resume_text, score)
                tailored_suggestions = generate_tailored_suggestions(resume_text, missing_keywords, section_scores)
                
                feedback = generate_feedback(score, matches, missing_keywords, vcs, readability, missing_entities, formatting_feedback, rsp, rsp_label, section_scores, tailored_suggestions, industry, resume_text, detected_ats)
            except Exception as e:
                feedback = f"Error processing resume: {str(e)}"
                logger.error(f"Error in index route: {str(e)}")
    
    logger.debug(f"Rendering template with resume_text: {resume_text[:50]}...")
    return render_template('index.html', feedback=feedback, resume_text=resume_text, job_description=job_description, industry=industry, ats_system=ats_system)

@app.route('/edit', methods=['GET', 'POST'])
def edit_resume():
    resume_text = request.form.get('resume_text', '') if request.method == 'POST' else ''
    job_description = request.form.get('job_description', '') if request.method == 'POST' else ''
    industry = request.form.get('industry', 'Tech') if request.method == 'POST' else 'Tech'
    ats_system = request.form.get('ats_system', 'Generic') if request.method == 'POST' else 'Generic'
    feedback = None
    
    logger.debug(f"Entering edit route - resume_text: {resume_text[:50]}...")
    
    if request.method == 'POST':
        if not resume_text or not job_description:
            feedback = "Error: Please provide both resume text and job description."
            logger.warning("Missing resume_text or job_description in edit route")
        else:
            try:
                score, matches, missing_keywords, vcs, readability, _, section_scores = calculate_ats_score(resume_text, job_description, 'en', ats_system)
                formatting_feedback, _ = check_formatting_and_dialect(resume_text, job_description, ats_system)
                tailored_suggestions = generate_tailored_suggestions(resume_text, missing_keywords, section_scores)
                feedback = f"Live ATS Score: {score:.2f}/100\nSkills Gap: {', '.join(list(missing_keywords)[:5])}\nSuggestions:\n" + "\n".join(tailored_suggestions)
            except Exception as e:
                feedback = f"Error processing resume: {str(e)}"
                logger.error(f"Error in edit route: {str(e)}")
    else:
        feedback = "Please enter resume text and job description to edit."
    
    return render_template('index.html', feedback=feedback, resume_text=resume_text, job_description=job_description, edit_mode=True, industry=industry, ats_system=ats_system)

if __name__ == "__main__":
    os.makedirs('uploads', exist_ok=True)
    logger.info("Starting Flask app")
    app.run(debug=True)