import psycopg2
from psycopg2 import OperationalError
from bs4 import BeautifulSoup
import requests
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import date, timedelta
import os
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import sys
import configparser
import time
from selenium.webdriver.chrome.options import Options

# The purpose of this automation is to extract all of the case numbers for a day 5 business days in the future, and put them into a txt file

# Set Chrome options to customize download behavior
chrome_options = Options()
# set the automation to run in the background instead of opening physically opening chrome
chrome_options.add_argument("--headless")
# finalize chrome settings
browser = webdriver.Chrome(options=chrome_options)

# get the file path of this script so that the sensitive information vault (config.ini) is locatable
script_dir = os.path.dirname(os.path.abspath(__file__))
config_file = os.path.join(script_dir, 'config.ini')

# configure and read the configuration file
config = configparser.ConfigParser()
config.read(config_file)

# default download directory:
host = config.get(
    'pgadmin credentials', 'host')
database = config.get(
    'pgadmin credentials', 'database')
user = config.get(
    'pgadmin credentials', 'user')
password = config.get(
    'pgadmin credentials', 'password')

# define the process of connecting to the postgres database

def open_connection_1(appendage):
    try:
        connection = psycopg2.connect(
            host=f'{host}',
            database=f'{database}',
            user=f'{user}',
            password=f'{password}'
        )
    except OperationalError as e:
        print(f"Error: {e}")

    cursor = connection.cursor()
    cursor.execute(appendage)
    connection.commit()


def open_connection_2(appendage, first_website):
    try:
        connection = psycopg2.connect(
            host=f'{host}',
            database=f'{database}',
            user=f'{user}',
            password=f'{password}'
        )
    except OperationalError as e:
        print(f"Error: {e}")

    cursor = connection.cursor()
    cursor.execute(appendage, (first_website,))
    result = cursor.fetchone()
    if result:
        # Extract the value from the tuple
        return result[0]

# define process of 'wait until element is visible'


def wait_until_element_visible(xpath, timeout=30):
    WebDriverWait(browser, timeout).until(
        EC.visibility_of_element_located((By.XPATH, xpath)))


# open the case number website finder
browser.get("https://legacy.utcourts.gov/cal/")

# get the current date and add 5 to the day
formatted_date = date.today()
formatted_date = formatted_date + timedelta(days=5)
# it will try the current date + 5 but if a weekend or holiday interferes, it will choose the next available date
while True:
    try:
        # is current date +5 visible?
        browser.find_element(By.XPATH,
                             f"//div[@id='date']/select/option[@value='{formatted_date}']")
        break
    # if the current date + 5 is not available, it will keep adding 1 to the date and trying again until it locates an available date
    except NoSuchElementException:
        formatted_date = formatted_date + timedelta(days=1)

# create a table within the database and name it the date that will be searched
create_table = f'''
    CREATE TABLE "{formatted_date}"(id SERIAL PRIMARY KEY);
    INSERT INTO "{formatted_date}" (id)
    SELECT generate_series(1, 1000);
'''
open_connection_1(create_table)


def is_element_visible(xpath):
    return bool(browser.find_elements(By.XPATH, xpath))


def setter(x):
    court_location_counter = 1
    court_location_type = x
    return court_location_counter, court_location_type


court_location_counter, court_location_type = setter('District')

original_location_names_list = []
new_location_names_list = []

while True:
    xpath = f'//optgroup[@label = "{court_location_type} Court Calendars"]/option[{court_location_counter}]'
    location_name = f"{court_location_type} {browser.find_element(By.XPATH, xpath).text}"
    original_location_name = browser.find_element(By.XPATH, xpath).text
    print(f"Searching {location_name}...")

    # select location
    wait_until_element_visible(xpath, timeout=30)
    browser.find_element(By.XPATH, xpath).click()

    # select date
    browser.find_element(
        By.XPATH, f"//div[@id='date']/select/option[@value='{formatted_date}']").click()

    # click search calendars
    browser.find_element(
        By.XPATH, "//input[@value='Search Calendars']").click()

    seconds = 0
    break_loop = False
    continue_loop = False

    while seconds <= 30:
        time.sleep(1)
        seconds = seconds + 1
        if seconds == 30:
            browser.refresh()
            continue_loop = True
        visibility = is_element_visible("(//div[@class='case'])[1]")
        if visibility:
            break
        # if there are no cases, the code will tell the user and continue on to the next location
        visibility = is_element_visible(
            "//*[contains(text(), 'No results found. Try searching again.')]")
        if visibility:
            print(
                f"There are no cases for date: {formatted_date} and location: {location_name}")
            court_location_counter = court_location_counter + 1
            visibility = is_element_visible(
                f'//optgroup[@label = "{court_location_type} Court Calendars"]/option[{court_location_counter}]')
            if not visibility:
                break_loop = True
            continue_loop = True
            break

    if break_loop:
        break
    elif continue_loop:
        continue

    second_website_name = f'''
        SELECT "Second Website"
        FROM court_location_correct_names
        WHERE "First Website" = %s
    '''
    first_website_name = f'{original_location_name}'
    result = open_connection_2(second_website_name, first_website_name)

    new_location_names_list.append(result)
    original_location_names_list.append(original_location_name)

    # get the current website url and use it to read the website's html
    new_url = browser.current_url
    response = requests.get(new_url)

    # Parse the HTML content of the site using BeautifulSoup
    soup = BeautifulSoup(response.content, "html.parser")

    # Get all the HTML for all the case numbers
    case_number_elements = soup.find_all("div", class_="case")

    # Iterate over the found elements and extract the numbers
    all_numbers = []
    for element in case_number_elements:
        # Use regex to find numbers in the text (btw... get_text only gets the text of one element.. that's why it's in a loop)
        numbers = re.findall(r'\d+', element.get_text())
        for number in numbers:
            all_numbers.append(number)
# -=-=-=-=--=-=-=-=-=--=-=-

    append_column = f'''
        ALTER TABLE "{formatted_date}"
        ADD COLUMN "{location_name}" VARCHAR(20);
    '''
    open_connection_1(append_column)

    case_number_counter = 0
    for number in all_numbers:
        case_number_counter = case_number_counter + 1
        append_row = f'''
            UPDATE "{formatted_date}"
            SET "{location_name}" = '{number}'
            WHERE id = {case_number_counter};
        '''
        open_connection_1(append_row)

    # !!!!!!!Check if the folder already exists, if not, create it!!!!!!!!

    court_location_counter = court_location_counter + 1
    visibility = is_element_visible(
        f'//optgroup[@label = "{court_location_type} Court Calendars"]/option[{court_location_counter}]')
    if not visibility and court_location_type == 'District':
        court_location_counter, court_location_type = setter('Justice')
    elif not visibility and court_location_type == 'Justice':
        break

# order the id column in ascending order so that the table is visually organized
order_table = f'''
    SELECT * FROM "{formatted_date}"
    ORDER BY id;
'''
open_connection_1(order_table)

print("\n\nDone!\n\n")

print(new_location_names_list)
print(original_location_names_list)
