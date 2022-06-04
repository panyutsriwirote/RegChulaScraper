# Selenium webdriver
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
# Command line argument parser
from argparse import ArgumentParser
# Other utilities
from tqdm import tqdm
import json
import re
# Define argument parser
parser = ArgumentParser(description="A tool for scraping course information from reg.chula.ac.th")
id_or_all = parser.add_mutually_exclusive_group(required=True)
id_or_all.add_argument("-id", nargs="+",
                    help="list of course IDs, each with length between 2 and 7")
id_or_all.add_argument("-all", action="store_true",
                    help="scrape every available course")
parser.add_argument("-p", choices=("S", "T", "I"), default="S",
                    help="study program: S = bisemester (default), T = trisemester, I = international")
parser.add_argument("-s", choices=("1", "2", "3"),
                    help="semester, default is the current semester")
parser.add_argument("-y",
                    help="academic year, default is the current academic year")
parser.add_argument("-g", action="store_true",
                    help="scrape group courses instead of normal courses")
parser.add_argument("-gui", action="store_true",
                    help="enable browser's GUI")
parser.add_argument("-o", default="regchula_courses.json",
                    help="output file's name, default is regchula_courses.json")
# Parse command line arguments
args = parser.parse_args()
id_arg = args.id
if id_arg is not None:
    for elem in id_arg:
        if not 1 < len(elem) < 8:
            print(f"{elem}: Course IDs must have length between 2 and 7")
            exit()
study_program_arg = args.p
semester_arg = args.s
academic_year_arg = args.y
group_course_mode = args.g
headless = not args.gui
output_file = args.o
# Set driver's options
options = webdriver.ChromeOptions()
options.headless = headless
# Start scraping
with webdriver.Chrome(options=options) as driver:
    # Open the page and go to the top frame
    driver.get("https://cas.reg.chula.ac.th/cu/cs/QueryCourseScheduleNew/index.html")
    driver.switch_to.frame("cs_search")
    # Identify relevant input fields
    study_program = Select(driver.find_element(By.ID, "studyProgram"))
    semester = Select(driver.find_element(By.ID, "semester"))
    academic_year = driver.find_element(By.ID, "acadyearEfd")
    course_no = driver.find_element(By.ID, "courseno")
    faculty = Select(driver.find_element(By.ID, "faculty"))
    course_type = Select(driver.find_element(By.ID, "coursetype"))
    submit = driver.find_element(By.NAME, "submit")
    # Input some values
    study_program.select_by_value(study_program_arg)
    if semester_arg is not None:
        semester.select_by_value(semester_arg)
    if academic_year_arg is not None:
        academic_year.clear()
        academic_year.send_keys(academic_year_arg)
    if group_course_mode:
        course_type.select_by_value("2")
    # Get a list of possible search term
    search_terms = [option.get_attribute("value") for option in faculty.options[1:]]
    if id_arg is not None:
        for elem in id_arg:
            faculty_code = elem[:2]
            if faculty_code not in search_terms:
                print(f"Faculty code {faculty_code} does not exist")
                exit()
        search_terms = id_arg
    n_term = len(search_terms)
    # Define alert-aware clicking
    def safe_click(element):
        element.click()
        try:
            alert = WebDriverWait(driver, 0.5).until(EC.alert_is_present())
            if alert.text == "ไม่มีข้อมูลตารางสอนตารางสอบ":
                print("No information is available for the specified parameters")
                exit()
            alert.accept()
            safe_click(element)
        except TimeoutException:
            pass
    # Begin writing JSON file
    with open(output_file, "w", encoding="utf-8") as file:
        file.write("[\n")
        if not group_course_mode:
            # Thai-month-to-num dictionary
            month_to_num = {"ม.ค.": "1",
                            "ก.พ.": "2",
                            "มี.ค.": "3",
                            "เม.ย.": "4",
                            "พ.ค.": "5",
                            "มิ.ย.": "6",
                            "ก.ค.": "7",
                            "ส.ค.": "8",
                            "ก.ย.": "9",
                            "ต.ค.": "10",
                            "พ.ย.": "11",
                            "ธ.ค.": "12"}
            # Pre-compile regex
            id_and_short_name = re.compile("^(\d{7})  (.+)$")
            credit_pattern = re.compile("^(\d+\.[05]|\-) CREDIT HOURS =  (.+)$")
            normal_detailed_credit = re.compile("^\(.+\)$")
            special_detailed_credit = re.compile("^\((.+)\)  (.+)$")
            tdf = re.compile("^TDF")
            exam_date = re.compile("^(\d{1,2}) (.+\..+\.) (\d{4}) เวลา (\d{1,2}:\d{2})\-(\d{1,2}:\d{2}) น\.$")
            # Loop through every search term
            for i, search_term in enumerate(search_terms, 1):
                # Submit the form and switch to the left frame
                course_no.clear()
                course_no.send_keys(search_term)
                safe_click(submit)
                print(f"Scraping {search_term} ({i}/{n_term})")
                driver.switch_to.parent_frame()
                driver.switch_to.frame("cs_left")
                # If there are no courses, continue with the next search term
                try:
                    course_list = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.ID, "Table4")))
                except TimeoutException:
                    print("No courses...")
                    driver.switch_to.parent_frame()
                    driver.switch_to.frame("cs_search")
                    continue
                # Loop through every course link
                rows = course_list.find_elements(By.TAG_NAME, "a")
                n_rows = len(rows)
                for j in tqdm(range(n_rows)):
                    # Click the link and switch to the right frame
                    link = rows[j]
                    link.click()
                    driver.switch_to.parent_frame()
                    driver.switch_to.frame("cs_right")
                    # The result should be a html form element with 5 child tables
                    course_info = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "form")))
                    child_tables = course_info.find_elements(By.TAG_NAME, "table")
                    # Identify relevant child tables
                    name_info = child_tables[1].find_elements(By.TAG_NAME, "tr")[3:]
                    credit_info = child_tables[2].find_elements(By.TAG_NAME, "tr")
                    exam_info = child_tables[3].find_elements(By.TAG_NAME, "font")
                    table_rows = child_tables[4].find_elements(By.TAG_NAME, "tr")[2:]
                    # Extract name information
                    match = id_and_short_name.match(name_info[0].text)
                    course_id = match.group(1)
                    course_short_name = match.group(2)
                    course_th_name = name_info[1].text
                    course_en_name = name_info[2].text
                    # Extract credit information
                    match = credit_pattern.match(credit_info[0].text)
                    credit = match.group(1)
                    credit = None if credit == "-" else float(credit)
                    credit_type = match.group(2).strip()
                    if credit_type == "(S/U)":
                        credit_type = "S/U"
                    third_row = credit_info[1].text
                    if not third_row:
                        detailed_credit_type = None
                    elif normal_detailed_credit.match(third_row):
                        detailed_credit_type = third_row[1:-1]
                    else:
                        match = special_detailed_credit.match(third_row)
                        detailed_credit_type = f"{match.group(1)} ({match.group(2)})"
                    prerequisite = credit_info[2].find_elements(By.TAG_NAME, "font")[1].text
                    if prerequisite == "-":
                        prerequisite = None
                    # Extract exam date information
                    mid_term = exam_info[1].text
                    if tdf.match(mid_term):
                        mid_term_date = mid_term_start = mid_term_end = None
                    else:
                        match = exam_date.match(mid_term)
                        mid_term_date = f"{match.group(3)}-{month_to_num[match.group(2)]}-{match.group(1)}"
                        mid_term_start = match.group(4)
                        mid_term_end = match.group(5)
                    final = exam_info[3].text
                    if tdf.match(final):
                        final_date = final_start = final_end = None
                    else:
                        match = exam_date.match(final)
                        final_date = f"{match.group(3)}-{month_to_num[match.group(2)]}-{match.group(1)}"
                        final_start = match.group(4)
                        final_end = match.group(5)
                    # Turn the table into an array
                    table = []
                    for table_row in table_rows:
                        columns = table_row.find_elements(By.TAG_NAME, "td")
                        table.append([column.text for column in columns])
                    # Process the array into sections and slots
                    section = []
                    offset = 0
                    for row in table:
                        if len(row) == 10:
                            sect_num = int(row[1]) 
                            sect_status = 1 if not row[0] else 0
                            registered, maximum = row[9].split('/')
                            section.append({"sect_num": sect_num,
                                            "sect_status": sect_status,
                                            "registered": int(registered),
                                            "maximum": int(maximum),
                                            "slot": []})
                            cur_slot_array = section[-1]["slot"]
                        elif len(row) == 8:
                            offset = -1
                        teaching_method = row[2+offset]
                        day = row[3+offset]
                        time = row[4+offset]
                        building = row[5+offset]
                        room = row[6+offset]
                        teacher = row[7+offset]
                        note = row[8+offset]
                        if not note:
                            note = None
                        cur_slot_array.append({"slot_id": len(cur_slot_array)+1,
                                                "teaching_method": teaching_method,
                                                "day": day,
                                                "time": time,
                                                "building": building,
                                                "room": room,
                                                "teacher": teacher,
                                                "note": note})
                        offset = 0
                    # JSONify and write to file
                    json_string = json.dumps({"course_id": course_id,
                                            "course_short_name": course_short_name,
                                            "course_th_name": course_th_name,
                                            "course_en_name": course_en_name,
                                            "credit": credit,
                                            "credit_type": credit_type,
                                            "detailed_credit_type": detailed_credit_type,
                                            "prerequisite": prerequisite,
                                            "mid_term_date": mid_term_date,
                                            "mid_term_start": mid_term_start,
                                            "mid_term_end": mid_term_end,
                                            "final_date": final_date,
                                            "final_start": final_start,
                                            "final_end": final_end,
                                            "section": section},
                                            indent="\t")
                    file.write(f"{json_string},\n")
                    # Continue with the next link
                    driver.switch_to.parent_frame()
                    driver.switch_to.frame("cs_left")
                # Continue with the next search term
                driver.switch_to.parent_frame()
                driver.switch_to.frame("cs_search")
        else: #Group course mode
            # Loop through every search term
            for i, search_term in enumerate(search_terms, 1):
                # Submit the form and switch to the left frame
                course_no.clear()
                course_no.send_keys(search_term)
                safe_click(submit)
                print(f"Scraping {search_term} ({i}/{n_term})")
                driver.switch_to.parent_frame()
                driver.switch_to.frame("cs_left")
                # If there are no courses, continue with the next search term
                try:
                    course_list = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.ID, "Table4")))
                except TimeoutException:
                    print("No courses...")
                    driver.switch_to.parent_frame()
                    driver.switch_to.frame("cs_search")
                    continue
                # Loop through every course link
                rows = course_list.find_elements(By.TAG_NAME, "a")
                n_rows = len(rows)
                for j in tqdm(range(n_rows)):
                    # Click the link and switch to the right frame
                    link = rows[j]
                    group_course_id = link.text
                    link.click()
                    driver.switch_to.parent_frame()
                    driver.switch_to.frame("cs_right")
                    # The result should be a html form element with lots of child tables, "Table1" is what we need
                    group_course_info = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "Table1")))
                    relevant_rows = group_course_info.find_elements(By.TAG_NAME, "tr")[1:]
                    # Extract sub-course information
                    sub_courses = []
                    for row in relevant_rows:
                        columns = row.find_elements(By.TAG_NAME, "td")
                        course_id = columns[0].text
                        sect_num = columns[2].text
                        sub_courses.append({"course_id": course_id,
                                            "sect_num": sect_num})
                    # JSONify and write to file
                    json_string = json.dumps({"group_course_id": group_course_id,
                                            "sub_courses": sub_courses},
                                            indent="\t")
                    file.write(f"{json_string},\n")
                    # Continue with the next link
                    driver.switch_to.parent_frame()
                    driver.switch_to.frame("cs_left")
                # Continue with the next search term
                driver.switch_to.parent_frame()
                driver.switch_to.frame("cs_search")
        # Replace the last ",\n" with "\n]"
        file.seek(file.tell()-3)
        file.write("\n]")
    print("Scraping Finished")