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

    def extract_posted(detail_soup):
        posted_tag = detail_soup.find(string=re.compile(r"Posted.*|Diposting.*|diunggah.*", re.IGNORECASE))
        if posted_tag:
            date_match = re.search(r'(\d{1,2}\s+\w+\s+\d{4})', posted_tag)
            if date_match:
                try:
                    return datetime.strptime(date_match.group(1), "%d %B %Y").strftime("%Y-%m-%d")
                except:
                    pass
        return datetime.now().strftime("%Y-%m-%d")

    def get_detail_posted(url):
        try:
            res = requests.get(url, headers=headers)
            soup = BeautifulSoup(res.text, 'html.parser')
            return extract_posted(soup)
        except:
            return datetime.now().strftime("%Y-%m-%d")

    sources = [
        ("Urbanhire", "https://www.urbanhire.com/jobs", ".job-title a", lambda c: (c.text.strip(), c['href'], c.find_parent('div', class_='job-list-item').select_one(".company-name"))),
        ("Kalibrr", "https://www.kalibrr.com/job-board/te", "a.kalibrr-job-list-card", lambda c: (
            c.select_one("h3").text.strip() if c.select_one("h3") else "No title",
            "https://www.kalibrr.com" + c['href'],
            c.select_one("h4").text.strip() if c.select_one("h4") else "Unknown")
        ),
        ("Glints", "https://glints.com/id/opportunities/jobs/explore?country=ID", "a[href*='/id/opportunities/jobs']", lambda c: (
            c.get("aria-label", "No title"),
            "https://glints.com" + c['href'],
            "Glints")
        ),
        ("Jobstreet", "https://id.jobstreet.com/id/jobs", "article", lambda c: (
            c.select_one("h1,h2,h3").text.strip() if c.select_one("h1,h2,h3") else "No title",
            "https://www.jobstreet.co.id" + c.find('a')['href'],
            c.select_one(".FYwKg._1nRJo").text.strip() if c.select_one(".FYwKg._1nRJo") else "Jobstreet")
        ),
        ("Karir", "https://karir.com/search-lowongan", "a[data-testid='job-card-title']", lambda c: (
            c.text.strip(),
            c['href'],
            "Karir")
        ),
        ("Loker.id", "https://www.loker.id/cari-lowongan-kerja", "h3.entry-title a", lambda c: (
            c.text.strip(),
            c['href'],
            "Loker.id")
        ),
        ("LinkedIn", "https://www.linkedin.com/jobs/search?keywords=Admin&location=Indonesia", "a.result-card__full-card-link", lambda c: (
            c.text.strip(),
            c['href'],
            "LinkedIn")
        ),
        ("Glassdoor", "https://www.glassdoor.com/Job/index.htm", "a.jobLink", lambda c: (
            c.text.strip(),
            "https://www.glassdoor.com" + c['href'],
            "Glassdoor")
        ),
        ("Indeed", "https://www.indeed.com/q-remote-jobs.html", "a[data-hiring-event]", lambda c: (
            c.text.strip(),
            "https://www.indeed.com" + c['href'],
            "Indeed")
        )
    ]

    for name, url, selector, parser in sources:
        try:
            log(f"Scraping {name}...")
            res = requests.get(url, headers=headers)
            soup = BeautifulSoup(res.text, 'html.parser')
            for card in soup.select(selector):
                title, link, company = parser(card)
                if not link.startswith('http'):
                    link = url + link
                posted = get_detail_posted(link)
                jobs.append({'title': title, 'link': link, 'company': company, 'posted': posted})
            log(f"Found {len(jobs)} total jobs after {name} scrape.")
        except Exception as e:
            log(f"Error scraping {name}: {e}")

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
            f"\u23F0 Posted: `{job['posted']}`\n"
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
