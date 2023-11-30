# -*- coding: UTF-8 -*-
import imaplib
import mailparser
from bs4 import BeautifulSoup
from openai import OpenAI
import logging
from pdfminer.high_level import extract_text
import mysql.connector
from sshtunnel import SSHTunnelForwarder

from config import EMAIL, PASSWORD, DIR , APIKEY ,SSH_PASSWORD, SSH_USERNAME, DATABASE_PASSWORD, DATABASE_USERNAME, SSH_HOST, DBNAME


ssh_host = SSH_HOST
ssh_username = SSH_USERNAME
ssh_password = SSH_PASSWORD
database_username = DATABASE_USERNAME
database_password = DATABASE_PASSWORD
database_name = DBNAME
localhost = '127.0.0.1'

tunnel = SSHTunnelForwarder(
        (ssh_host, 22),
        ssh_username = ssh_username,
        ssh_password = ssh_password,
        remote_bind_address = ('127.0.0.1', 3306)
    )

tunnel.start()

connection = mysql.connector.connect(
        host='127.0.0.1',
        user=database_username,
        passwd=database_password,
        db=database_name,
        port=tunnel.local_bind_port
    )

cursor = connection.cursor()


#Set your apikey for chat gpt
client = OpenAI(
    # defaults to os.environ.get("OPENAI_API_KEY")
    api_key=APIKEY,
)

#Where are we gonna save our file after work
OUTPUT_DIR = DIR

ai_responses = []  # List to save AI responses



def connect_to_gmail(username, password):
    """Connects to Gmail IMAP server"""
    M = imaplib.IMAP4_SSL('imap.gmail.com')
    M.login(username, password)
    M.select('inbox')
    return M


def fetch_all_emails(M):
    """Fetches all emails from the inbox"""
    #Change UNSEEN TO ALL for first time if needed
    result, data = M.search(None, 'UNSEEN')
    email_ids = data[0].split()
    return email_ids


def extract_email_fields(mail):
    """Extracts relevant fields from the email"""
    subject = str(mail.subject)
    sender = ''.join(map(str, mail.from_))
    date = str(mail.date)
    text = ''.join(map(str, mail.text_plain))
    text_html = ''
    #this thing exist for cases when for some reason we cant recive plain text from mail, so we get info with html
    if len(text) < 5:
        code_html = str(mail.text_html)
        soup = BeautifulSoup(code_html, 'html.parser')
        text_html = soup.get_text(separator=' ').strip()
    return subject, sender, date, text, text_html

def process_email(M, email_id):
    """Function to process a single email"""
    result, data = M.fetch(email_id, '(RFC822)')
    mail = mailparser.parse_from_bytes(data[0][1])

    subject, sender, date, text, text_html = extract_email_fields(mail)


    if text_html:
        return [subject, sender, date, text, text_html,mail]
    else:
        return [subject, sender, date, text, '',mail]



def parse_emails(username, password):
    """Main function to parse emails"""
    try:
        M = connect_to_gmail(username, password)
        email_ids = fetch_all_emails(M)

        email_data = []
        for email_id in email_ids:
            try:
                email_data.append(process_email(M, email_id))
            except Exception as e:
                logging.error(f"Failed to process email {email_id}: {str(e)}")
    except Exception as e:
        logging.error(f"Failed to connect or fetch emails: {str(e)}")
        return

    process_ai(email_data)

    M.close()
    M.logout()


def process_ai(email_data):
    """Function to perform AI processing on email data"""
    for data in email_data:
        subject = data[0]
        text = data[3]
        mail = data[5]
        if "Fwd:" in subject:
            sender = ""
            date = ""
            subject = subject.replace("Fwd:","") #delete useless info
            lines = text.split("\n")  # Split the email text into lines

            for line in lines:
                if line.startswith("From:") or line.startswith("От:"):
                    sender = line.replace("From:", "").replace("От:", "").strip()
                    sender = sender.replace("<","").replace(">","")
                elif line.startswith("Date:"):
                    date = line.replace("Date:", "").strip()
        else:
            sender = data[1]
            sender = sender.replace("<","").replace(">","")
            date = data[2]

        text_html = data[4]
        response_data = ''
        if text_html:
          text_for_gpt = text_html
        else:
          text_for_gpt = text

        retries = 0
        while retries < 3:
            try:
                print('pepeg')
                completion =  client.chat.completions.create(
                # gpt-4-0613
                # gpt-3.5-turbo
                messages = [{"role": "user", "content": f"Из предоставленного текст пожалуйста выпиши мне должность на которую пришёл запрос. Предоставь ответ только должностью.Предоставленный текст: {text}."}],
                model="gpt-3.5-turbo")
                # Extract the required information from the completion
                response_data = completion.choices[0].message.content
                response_data_list = []
                response_data_list.append(response_data)
                # time.sleep(20)
                if response_data:
                    #leave while because we got data
                    break

                retries += 1 #dont ask me why this exist,but without it it doesnt works for some reason, base of programing be like :P

                # Pause for 20 seconds (Api has limit for requsts in a minute,if we procces more then 3 mail it give us api error)
            except Exception as e:
                retries += 1
                logging.debug('Esception is %s', e)
                # time.sleep(20)

        if response_data_list:
            # Add the response to the list
            for response in response_data_list:
                combined_list = [response, sender, subject, date]
                ai_responses.append(combined_list)

    print(ai_responses)
    #save_ai_responses()  # Save AI responses after all emails are processed


#cvs_data
def save_ai_responses():
    """Saves AI responses to the database"""

    insert_sql = """INSERT INTO cvs_data (job_title, sender, subject, date) VALUES (%s, %s, %s, %s)"""


    for data in ai_responses:
        job_title, sender, subject, date = data

        # If not, insert the new data
        values = (job_title, sender, subject, date)
        cursor.execute(insert_sql, values)

    connection.commit()

    print("AI responses saved to the database")



# Run the program
# Setup logging
logging.basicConfig(filename='email_processing.log', level=logging.DEBUG)

username = EMAIL  #your mail here
password = PASSWORD  #your password for apps here
parse_emails(username, password)