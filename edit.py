<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Advanced ATS Optimizer</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            max-width: 800px;
            margin-left: auto;
            margin-right: auto;
        }
        h1 {
            color: #333;
        }
        h2 {
            color: #555;
        }
        form {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-top: 10px;
            font-weight: bold;
        }
        input[type="file"], textarea, select {
            width: 100%;
            padding: 8px;
            margin-top: 5px;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
        textarea {
            resize: vertical;
        }
        input[type="submit"] {
            background-color: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin-top: 10px;
        }
        input[type="submit"]:hover {
            background-color: #45a049;
        }
        pre {
            background-color: #f8f8f8;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            white-space: pre-wrap;
        }
        a {
            color: #0066cc;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <h1>Advanced ATS Optimizer</h1>
    <form method="post" enctype="multipart/form-data" action="/">
        <label for="resume">Resume (PDF/DOCX):</label>
        <input type="file" name="resume" id="resume" accept=".pdf,.docx"><br>
        
        <label for="job_description">Job Description:</label>
        <textarea name="job_description" id="job_description" rows="5" placeholder="Paste the job description here">{{ job_description }}</textarea><br>
        
        <label for="industry">Industry:</label>
        <select name="industry" id="industry">
            <option value="Tech" {% if industry == 'Tech' %}selected{% endif %}>Tech</option>
            <option value="Finance" {% if industry == 'Finance' %}selected{% endif %}>Finance</option>
            <option value="Healthcare" {% if industry == 'Healthcare' %}selected{% endif %}>Healthcare</option>
        </select><br>
        
        <label for="ats_system">ATS System:</label>
        <select name="ats_system" id="ats_system">
            <option value="Generic" {% if ats_system == 'Generic' %}selected{% endif %}>Generic</option>
            <option value="Taleo" {% if ats_system == 'Taleo' %}selected{% endif %}>Taleo</option>
            <option value="Workday" {% if ats_system == 'Workday' %}selected{% endif %}>Workday</option>
            <option value="Greenhouse" {% if ats_system == 'Greenhouse' %}selected{% endif %}>Greenhouse</option>
            <option value="iCIMS" {% if ats_system == 'iCIMS' %}selected{% endif %}>iCIMS</option>
            <option value="BrassRing" {% if ats_system == 'BrassRing' %}selected{% endif %}>BrassRing</option>
        </select><br>
        
        <input type="submit" value="Analyze">
    </form>

    {% if edit_mode %}
        <h2>Edit Resume</h2>
        <form method="post" action="/edit">
            <label for="resume_text">Resume Text:</label>
            <textarea name="resume_text" id="resume_text" rows="10" placeholder="Paste or edit your resume text here">{{ resume_text }}</textarea><br>
            
            <input type="hidden" name="job_description" value="{{ job_description }}">
            <input type="hidden" name="industry" value="{{ industry }}">
            <input type="hidden" name="ats_system" value="{{ ats_system }}">
            <input type="submit" value="Update">
        </form>
    {% endif %}

    {% if feedback %}
        <h2>Analysis</h2>
        <pre>{{ feedback }}</pre>
    {% endif %}

    <a href="/edit">Edit Resume</a>
</body>
</html>