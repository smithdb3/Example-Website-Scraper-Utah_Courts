# the purpose of this automation is to locate all of the case information for the current date and insert the information into airtable

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import time
import re
from datetime import date, timedelta
from airtable import airtable
from selenium.common.exceptions import TimeoutException
import boto3
from selenium.webdriver.chrome.options import Options
import os
import configparser


# *** Variables ***

# get the file path of this script so that the sensitive information vault (config.ini) is locatable
script_dir = os.path.dirname(os.path.abspath(__file__))
config_file = os.path.join(script_dir, 'config.ini')

# configure and read the configuration file
config = configparser.ConfigParser()
config.read(config_file)

# get all the sensitive information and set them to secure variables

# default download directory
download_directory = config.get(
    'default download directory', 'download_directory')

# XChange case search credentials
username = config.get('XChange case search credentials', 'username')
password = config.get('XChange case search credentials', 'password')

# airtable credentials
airtable_table_name = config.get(
    'airtable API credentials', 'airtable_table_name')
airtable_base_id = config.get('airtable API credentials', 'airtable_base_id')
airtable_API_key = config.get('airtable API credentials', 'airtable_API_key')

# amazon s3 credentials
bucket_name = config.get('amazon s3 API credentials', 'bucket_name')
s3_access_key_id = config.get('amazon s3 API credentials', 's3_access_key_id')
s3_secret_access_key = config.get(
    'amazon s3 API credentials', 's3_secret_access_key')


# Set Chrome options to customize download behavior
chrome_options = Options()

# Specify the default download directory (so that when the case document is downloaded, it is saved to a known location)
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": download_directory,
})

# specify browser as chrome with the above settings applied
browser = webdriver.Chrome(options=chrome_options)

# define future "list" variables
no_sentence_date_log = []
failure_log = []
failed_cases = []

# define process of 'wait until element is visible'


def wait_until_element_visible(xpath, timeout=30):
    WebDriverWait(browser, timeout).until(
        EC.visibility_of_element_located((By.XPATH, xpath)))

# Get the current date (that is the name of the file that contains the list of case numbers)


# ****** ORIGINAL CODE ==== current_date = date.today()
current_date = date.today()
current_date = current_date + timedelta(days=1)
# ******

# Initialize a list to store the case numbers
all_numbers = []

# Open the file and read the case numbers
all_numbers_file = os.path.join(download_directory, f"{current_date}.txt")
with open(all_numbers_file, 'r') as file:
    for line in file:
        # Remove leading and trailing whitespaces and append the number to the list
        number = line.strip()
        all_numbers.append(number)

# open XChange Case Search website
browser.get("website_name")

# input username
wait_until_element_visible("//input[@id='username']", timeout=30)
browser.find_element(
    By.XPATH, "//input[@id='username']").send_keys(username)

# input password
browser.find_element(
    By.XPATH, "//input[@id='password']").send_keys(password)

# do captcha code
captcha = input("Please enter the code: ")
browser.find_element(
    By.XPATH, "//input[@placeholder='Enter the characters in the image above.']").send_keys(captcha)

# click login
browser.find_element(By.XPATH, "//input[@value='Login']").click()

# define variable to display what the case count is
case_counter = 0

# loop through the list of case numbers and retrieve the desired information
for number in all_numbers:
    # set and print the case number count
    case_counter = case_counter+1
    print(f"Searching case number {case_counter}: {number}")

    # start attempts at #1 and continue attempting to retrieve info until 3 attempts
    number_of_attempts = 1
    while number_of_attempts < 4:
        try:
            # define process of switching frames as the website changes
            def switch_main_frame():
                wait_until_element_visible(
                    "//frame[@name='mainFrame']", timeout=30)
                browser.switch_to.frame("mainFrame")
            # show attempts
            print(f"attempt #{number_of_attempts}")

        # Insert course case information

            # switch frames
            switch_main_frame()

            # enter jurisdiction
            wait_until_element_visible(
                "//option[contains(.,'District & Justice')]", 30)
            browser.find_element(
                By.XPATH, "//option[contains(.,'District & Justice')]").click()

            # enter case number
            wait_until_element_visible("//input[@id='caseNumber']", 30)
            case_number = browser.find_element(
                By.XPATH, "//input[@id='caseNumber']")
            case_number.send_keys(Keys.COMMAND + 'a')
            case_number.send_keys(Keys.BACKSPACE)
            case_number.send_keys(number)

            # enter search scope
            browser.find_element(
                By.XPATH, "//select[@id='searchScope']/option[contains(.,'Court Location')]").click()

            # enter location
            browser.find_element(
                By.XPATH, "//option[contains(.,'South Salt Lake Justice Court')]").click()

            # click search
            browser.find_element(
                By.XPATH, "(//input[@value='Search'])[2]").click()
            browser.switch_to.default_content()

            # Click on file
            switch_main_frame()
            wait_until_element_visible(
                "(//td[@data-label='Case Number'])[1]/a", 30)
            browser.find_element(
                By.XPATH, "(//td[@data-label='Case Number'])[1]/a").click()
            browser.switch_to.default_content()

            # define process of switching iframes
            def switch_iframe():
                wait_until_element_visible(
                    "//iframe//following::iframe", timeout=30)
                iframe_element = browser.find_element(
                    By.XPATH, "//iframe//following::iframe")
                browser.switch_to.frame(iframe_element)

        # Retrieve information from document that is needed for Airtable

            # switch frames
            switch_main_frame()
            switch_iframe()

            # search for the sentencing date
            wait_until_element_visible("//button[@id='viewFind']", 30)
            time.sleep(1)
            browser.find_element(By.XPATH, "//button[@id='viewFind']").click()
            wait_until_element_visible("//input[@id='findInput']", 30)
            search_bar = browser.find_element(
                By.XPATH, "//input[@id='findInput']")
            search_bar.send_keys("Minute Entry - SENTENCE")

            # if sentencing date exists, get the text
            try:
                wait_until_element_visible(
                    "//span[contains(.,'Minute Entry - SENTENCE')]/preceding-sibling::span[2]", 5)
                element = browser.find_element(
                    By.XPATH, "//span[contains(.,'Minute Entry - SENTENCE')]/preceding-sibling::span[2]")
                sentencing_date = element.text
                sentencing_date_visible = True

            # if sentencing date does not exist, break the while loop and continue onto the next case number before moving on
            except:
                sentencing_date_visible = False
            if sentencing_date_visible == False:
                browser.refresh()
                browser.switch_to.default_content()
                no_sentence_date_log.append(number)
                break

            # if the sentencing date was present, the code will carry out the rest of its functions
            if sentencing_date_visible == True:

                # set the file path for the document once its downloaded
                original_file_path = os.path.join(
                    download_directory, "document.pdf")
                new_file_path = os.path.join(
                    download_directory, f"{number}.pdf")

                # Remove the file if it already exists
                if os.path.exists(original_file_path):
                    os.remove(original_file_path)
                if os.path.exists(new_file_path):
                    os.remove(new_file_path)

                # click download on the file
                wait_until_element_visible(
                    '//button[@id="download"]', timeout=30)
                browser.find_element(
                    By.XPATH, '//button[@id="download"]').click()

                # wait until file is visible before renaming it
                while not os.path.exists(original_file_path):
                    time.sleep(2)
                # Rename the file to a unique name (the case number) that can be used for a link in the future
                os.rename(original_file_path, new_file_path)

                # Get judge name
                element = browser.find_element(
                    By.XPATH, "//span[contains(.,'CURRENT ASSIGNED JUDGE')]/following-sibling::span[1]")
                judge_name = element.text

                # Get Charges
                charges_html_list = browser.find_elements(
                    By.XPATH, "//span[contains(.,'CURRENT ASSIGNED JUDGE')]/preceding::span[contains(.,'Charge')]")
                charges_list = []
                for element in charges_html_list:
                    charges_text = element.text
                    charges_list.append(charges_text)
                charges = "\n\n".join(charges_list)

                # find if there is plea in abeyance present in the document
                try:
                    WebDriverWait(browser, 1).until(EC.visibility_of_element_located(
                        (By.XPATH, "//span[contains(.,'Minute Entry - PLEA IN ABEYANCE')]")))
                    PIA = "Yes"
                except:
                    PIA = "No"

            # find if there was jail or prison time ordered
                # orient the page to have the jail/prison sentence frame visible
                search_bar.send_keys(Keys.COMMAND + 'a')
                search_bar.send_keys(Keys.BACKSPACE)
                search_bar.send_keys("SENTENCE JAIL")

                # see if jail sentence is present
                try:
                    element = WebDriverWait(browser, 2).until(
                        EC.visibility_of_element_located((By.XPATH, "//span[contains(.,'SENTENCE JAIL')]/following-sibling::span[1]")))
                    sentence_jail = element.text

                # if jail sentence is not present, see if prison sentence is present
                except TimeoutException:
                    try:
                        element = WebDriverWait(browser, 2).until(
                            EC.visibility_of_element_located((By.XPATH, "//span[contains(.,'SENTENCE PRISON')]/following-sibling::span[1]")))
                        sentence_jail = element.text

                    # if neither were present, 0 will be inputted into the table
                    except TimeoutException:
                        sentence_jail = '0'

            # Get Probation Months
                # see if the case has probation months
                try:
                    element = browser.find_element(
                        By.XPATH, "//span[contains(.,'ORDER OF PROBATION')]/following-sibling::span[1]")
                    # if it is present, only the number portion of the text will be retrieved
                    probation_months = re.findall(r'\d+', element.text)
                    probation_months = ", ".join(probation_months)

                # if there are no probation months present, 0 will be inputted to the table
                except:
                    probation_months = "0"

                # Click close on the document
                browser.switch_to.default_content()
                browser.switch_to.frame("mainFrame")
                browser.find_element(
                    By.XPATH, "//h4[contains(.,'Case History')]/following-sibling::button[@class='close']").click()
                browser.switch_to.default_content()

            # upload the pdf to amazon s3
                # Define the object name (name of the pdf that will be saved)
                object_name = f'{number}.pdf'

                # set the parameters for python package boto3 to communicate with the S3 API
                s3 = boto3.client('s3', aws_access_key_id=s3_access_key_id,
                                  aws_secret_access_key=s3_secret_access_key)

                # Upload the file to S3
                with open(new_file_path, 'rb') as file:
                    s3.upload_fileobj(file, bucket_name, object_name)

                # Get the S3 URL of the uploaded file
                file_url = f"https://{bucket_name}.s3.amazonaws.com/{object_name}"

            # add the case information to the cooresponding airtable fields
                # set the parameters for python package airtable to communicate with the Airtable API
                at = airtable.Airtable(
                    airtable_base_id, airtable_API_key)

                # assign what information will go to which field
                data = {
                    'Case Number': number,
                    'Sentencing Date': sentencing_date,
                    'Court': 'South Salt Lake City',
                    'Judge': judge_name,
                    'Charges': charges,
                    'PIA?': PIA,
                    'Jail/Prison Ordered?': sentence_jail,
                    'Probation Months': probation_months,
                    'Case Docket': [
                        {
                            'url': file_url
                        }
                    ]
                }

                # Create the record
                at.create(airtable_table_name, data)
                os.remove(new_file_path)

                # upon completion of this case number, break the while loop in that it remains on 'attempt 1'
                break

        # if there are any errors that occur, the code will stop where it happened and execute the following:
        except Exception as error:
            # print what error happened
            print("\nAn exception occurred:", type(error).__name__, "\n")
            # refresh the browser
            browser.refresh()
            browser.switch_to.default_content()
            # set the new attempt number
            number_of_attempts = number_of_attempts + 1

            # if this was the third attempt, the case number will be sent to the error log
            if number_of_attempts == 4:
                failure_log.append(number)

# Print log of case numbers without sentencing dates
print("\n\nCase Numbers without sentencing dates:\n\n")
# Make the log legible then print the log
no_sentence_date_log = "\n ".join(no_sentence_date_log)
print(no_sentence_date_log)

# Print log of all case numbers that failed to be registered
if failure_log == []:
    # print the following if there were no failures
    print("\n\nCase numbers that are undocumented because the bot encountered pageload or webnavigation errors:\n\nThere were no case errors!\n\n")
else:
    print("\n\nCase numbers that are undocumented because the bot encountered pageload or webnavigation errors:\n\n")
    # Make the log legible then print the log
    failure_log_str = "\n ".join(failure_log)
    print(failure_log_str)
