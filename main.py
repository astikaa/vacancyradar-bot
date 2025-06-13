import requests
from bs4 import BeautifulSoup
from telegram import Bot
import json
import os

# --- CONFIG ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
JOB_SITE_URL = 'https://www.loker.id/'
SAVED_JOBS_FILE = 'saved_jobs.json'

# --- INIT ---
bot = Bot(token=TELEGRAM_TOKEN)

# --- Load previously saved jobs ---
def load_saved_jobs():
    if os.path.exists(SAVED_JOBS_FILE):
        with open(SAVED_JOBS_FILE, 'r') as f:
            return json.load(f)
    return []

# --- Save jobs ---
def save_jobs(jobs):
    with open(SAVED_JOBS_FILE, 'w') as f:
        json.dump(jobs, f)

# --- Scrape all jobs from Loker.id ---
def scrape_jobs():
    response = requests.get(JOB_SITE_URL)
    soup = BeautifulSoup(response.text, 'html.parser')

    jobs = []
    for post in soup.select('.post-content'):
        try:
            title = post.select_one('.post-title a').text.strip()
            link = post.select_one('.post-title a')['href']
            company = post.select_one('.company').text.strip()
            jobs.append({'title': title, 'link': link, 'company': company})
        except:
            continue
    return jobs

# --- Filter jobs based on keywords ---
def filter_jobs(jobs, keywords=None):
    if not keywords:
        return jobs
    filtered = []
    for job in jobs:
        text = f"{job['title']} {job['company']}".lower()
        if any(keyword.lower() in text for keyword in keywords):
            filtered.append(job)
    return filtered

# --- Send new jobs to Telegram ---
def notify_new_jobs(new_jobs):
    for job in new_jobs:
        message = (
            f"📡 [VacancyRadar]\n"
            f"💼 Posisi: *{job['title']}*\n"
            f"🏢 Perusahaan: _{job['company']}_\n"
            f"🔗 {job['link']}"
        )
        bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='Markdown')

# --- Main ---
def main():
    keywords = ["remote", "freelance", "admin", "marketing", "python"]  # You can customize this
    saved = load_saved_jobs()
    current = scrape_jobs()

    saved_links = {job['link'] for job in saved}
    new_jobs = [job for job in current if job['link'] not in saved_links]
    filtered_jobs = filter_jobs(new_jobs, keywords)

    if filtered_jobs:
        notify_new_jobs(filtered_jobs)
        save_jobs(current)

if __name__ == '__main__':
    main()
