import requests
from bs4 import BeautifulSoup
import json
import os
import re
from dotenv import load_dotenv
from datetime import datetime

# --- Load .env file ---
load_dotenv()

# --- CONFIG ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
SAVED_JOBS_FILE = 'saved_jobs.json'
MAX_JOBS_TO_SEND = 5

# --- Helper log function ---
def log(message):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {message}")

# --- Escape Markdown special characters ---
def escape_md(text):
    return re.sub(r'([*_`\[\]()])', r'\\\1', text)

# --- Load previously saved jobs ---
def load_saved_jobs():
    if os.path.exists(SAVED_JOBS_FILE):
        with open(SAVED_JOBS_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                log("Warning: saved_jobs.json is empty or corrupted. Starting fresh.")
                return []
    return []

# --- Save jobs ---
def save_jobs(jobs):
    with open(SAVED_JOBS_FILE, 'w') as f:
        json.dump(jobs, f)
    log(f"Saved {len(jobs)} jobs to file.")

# --- Clear jobs older than 7 days ---
def clear_old_jobs():
    saved_jobs = load_saved_jobs()
    filtered_jobs = []
    for job in saved_jobs:
        job_time = job.get('timestamp')
        if job_time:
            try:
                dt = datetime.strptime(job_time, "%Y-%m-%d %H:%M:%S")
                if (datetime.now() - dt).days <= 7:
                    filtered_jobs.append(job)
            except ValueError:
                continue
    save_jobs(filtered_jobs)
    log(f"Cleared old jobs, {len(filtered_jobs)} recent jobs kept.")

# --- Scrape jobs from multiple sources ---
def scrape_jobs():
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    # Existing sources...
    # (Glints, Jobstreet, Karir, Loker.id, LinkedIn, Glassdoor, Indeed)

    # --- Urbanhire ---
    try:
        log("Scraping Urbanhire...")
        res = requests.get("https://www.urbanhire.com/jobs", headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        for card in soup.select(".job-title a"):
            title = card.text.strip()
            link = card['href'] if card['href'].startswith('http') else "https://www.urbanhire.com" + card['href']
            company_tag = card.find_parent('div', class_='job-list-item').select_one(".company-name")
            company = company_tag.text.strip() if company_tag else "Unknown"
            jobs.append({'title': title, 'link': link, 'company': company})
        log(f"Found {len(jobs)} total jobs after Urbanhire scrape.")
    except Exception as e:
        log(f"Error scraping Urbanhire: {e}")

    # --- Kalibrr ---
    try:
        log("Scraping Kalibrr...")
        res = requests.get("https://www.kalibrr.com/job-board/te", headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        for card in soup.select("a.kalibrr-job-list-card"):
            title = card.select_one("h3").text.strip() if card.select_one("h3") else "No title"
            link = "https://www.kalibrr.com" + card['href']
            company = card.select_one("h4").text.strip() if card.select_one("h4") else "Unknown"
            jobs.append({'title': title, 'link': link, 'company': company})
        log(f"Found {len(jobs)} total jobs after Kalibrr scrape.")
    except Exception as e:
        log(f"Error scraping Kalibrr: {e}")

    return jobs

# --- Normalize links ---
def normalize_link(link):
    return link.split("?")[0].rstrip("/")

# --- Send new jobs to Telegram ---
def notify_new_jobs(new_jobs):
    for job in new_jobs:
        message = (
            f"\U0001F4E1 [VacancyRadar]\n"
            f"\U0001F4BC Posisi: *{escape_md(job['title'])}*\n"
            f"\U0001F3E2 Perusahaan: _{escape_md(job['company'])}_\n"
            f"\U0001F517 [Click for details]({job['link']})"
        )
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            data = {
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, data=data)
            if response.status_code == 200:
                log(f"Sent job: {job['title']}")
            else:
                log(f"Failed to send job: {job['title']} — {response.text}")
        except Exception as e:
            log(f"Error sending job to Telegram: {e}")

# --- Main ---
def main():
    log("Job scraper started.")
    clear_old_jobs()
    saved = load_saved_jobs()
    current = scrape_jobs()

    # Append timestamp to new jobs
    for job in current:
        job['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    saved_links = {normalize_link(job['link']) for job in saved}
    new_jobs = [job for job in current if normalize_link(job['link']) not in saved_links]
    new_jobs = new_jobs[:MAX_JOBS_TO_SEND]

    if new_jobs:
        notify_new_jobs(new_jobs)
        save_jobs(saved + new_jobs)
    else:
        log("No new jobs found.")

if __name__ == '__main__':
    main()
