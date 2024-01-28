from datetime import datetime, timedelta, time
import json
import requests

class AttendanceReport:

    def check_if_date_is_in_year(self, date_val, year):
        '''
            Helper method used to check that a string date is within the year specified 
            in the parameter. 
        '''
        date_year = int(date_val.split('-')[0])
        return date_year == year
    

    def remove_duplicate_events(self, event_data):
        '''
            Helper method to remove any duplicates of events which may be added to the list.
            An event may be added to the list more than once if multiple delinquent dates occurred 
            near the event date.
        '''
        unique_dates = set()
        unique_events = []

        for event in event_data:
            event_date = event["event_date"]
            if event_date not in unique_dates:
                unique_dates.add(event_date)
                unique_events.append(event)

        return unique_events
        
    
    def calculate_total_hours(self, start_time, stop_time):
        '''
            Helper method to calculate the difference in hours between two time strings
        '''
        start = datetime.strptime(start_time, "%H:%M:%S")
        stop = datetime.strptime(stop_time, "%H:%M:%S")
        duration = stop - start
        return duration.total_seconds() / 3600
    
        
    def calculate_average_hours_per_week(self, attendance_data):
        '''
            Method which takes in attendance data and iterates through the list. If an employee clocks in and out for a day,
            the hours are calculated and added to the hours total for the week the date belongs to. Once all the hours are calculated for
            all the weeks of the year, the average is found by dividing the total hours for the year by the number of weeks worked for the year.
            The average is returned.

        '''
        
        total_hours_per_week = {}

        for attendance in attendance_data:
            total_hours = 0
            if attendance['clock_in'] is not None and attendance['clock_out'] is not None:
                start_time = attendance["clock_in"]
                stop_time = attendance["clock_out"]
                total_hours = self.calculate_total_hours(start_time, stop_time)

            date = datetime.strptime(attendance["date"], "%Y-%m-%d")
            
            week_key = date.isocalendar().week
            
            if week_key not in total_hours_per_week:
                total_hours_per_week[week_key] = 0
            total_hours_per_week[week_key] += total_hours

        total_hours = sum(total_hours_per_week.values())

        
        return total_hours / len(total_hours_per_week)
    
    
    def get_employee_attendance_data(self, record_id, employee_attendance_data, year):
        '''
            Method which takes in the attendance data for all employees and creates a new list which only contains the attendance data 
            for the specified employee, using their record ID, within the specified year.
        '''
  
        employee_data = []
        for emp in employee_attendance_data:
            if emp["employee_record_id"] == record_id:
                if self.check_if_date_is_in_year(emp['date'], year):
                    employee_data.append(emp)

        return employee_data
    

    def check_employee_times(self, employee_attendance_data):
        '''
            Method which uses the employee's attendance data to check whether the time they clocked in is before 8:16 and the time they
            clocked out not before 16:00. If the times are not within those parameters or no time is recorded, it is stored as a delinquent attendance, i.e. 
            the employee arrived late, left early or did not show up. The list of delinquent attendances is returned.
        '''
        start_time = time(8,15,0)
        end_time = time(16,00,00)

        delinquent_data = []

        for attendance in employee_attendance_data:
            if attendance['clock_in'] is None and attendance['clock_out'] is None:
                delinquent_data.append(attendance['date'])
                continue

            clock_in = datetime.strptime(attendance['clock_in'], "%H:%M:%S").time()
            clock_out = datetime.strptime(attendance['clock_out'], "%H:%M:%S").time()
            
            
            if clock_in > start_time or clock_out < end_time:
                # print(attendance['clock_in'] +' '+ attendance['clock_out']+' '+attendance['date'])
                delinquent_data.append(attendance['date'])
        # print(json.dumps(delinquent_data, indent=4))
        return delinquent_data
    
    
    def check_dates_against_events(self, weather_data, events_data, poor_employee_attendance_data, country):
        '''
            Method which takes in weather data, events data, employee's poor attendance and the country of the employee. 
            It then filters the data appropriately and converts them to sets for faster comparisons.
            The delinquent days are checked against the weather data to remove any dates the employee may have been affected by bad weather.
            The remaining dates are then checked against the days events were held and if an event fell on, before or after a day the employee was
            delinquent, the event is recorded in a list.
        '''
        poor_employee_attendance_set = set(poor_employee_attendance_data)
        weather_set = {weather['date'] for weather in weather_data if weather['country'] == country and self.check_if_date_is_in_year(weather['date'], 2023) and (weather['condition'] in ['hail', 'thunderstorm', 'blizzard', 'hurricane'] or weather['max_temp'] > 40.0)}
        event_set = {(event['event_date'], event['event_name']) for event in events_data if event['country'] == country and self.check_if_date_is_in_year(event['event_date'], 2023)}
        
        

        no_weather_excuse = poor_employee_attendance_set - weather_set
        no_weather_excuse_list = list(no_weather_excuse)
        

        event_reason_list = []

        for no_excuse_date in no_weather_excuse_list:
            no_excuse_date_obj = datetime.strptime(no_excuse_date, "%Y-%m-%d").date()

            for event_date, event_name in event_set:
                
                event_date_obj = datetime.strptime(event_date, "%Y-%m-%d").date()
        
                difference = event_date_obj - no_excuse_date_obj
                
                if difference in [timedelta(days=-1), timedelta(days=0), timedelta(days=1)]:
                    event_reason = {
                        "country": country,
                        "event_name": event_name,
                        "event_date": event_date
                    }
                    event_reason_list.append(event_reason)
            
        event_reason_list = self.remove_duplicate_events(event_reason_list)

        return event_reason_list


    def identify_delinquent_employees(self, employee_file_name, attendance_file_name):
        '''
            Main method which takes in the employee data file name and attendance data file name.
            It calls the relevant APIs to assist.
            It then iterates over the employee list and for each employee it:
                - gets their country and uses their record ID to get their attendance for the year
                - gets all the poor attendances for the employee for the year
                - calculates the average hours worked per week
                - cross references the days delinquent with the events for that country within the year
                - checks if their were more than three instances of deliquency for the year
            If there were more than three instances, the employee's information is recorded as well as the events they may have attended and stored in a list. 
            The list is returned
        '''

        wayward_employees = []

        weather_url = "https://www.pingtt.com/exam/weather"
        events_url = "https://www.pingtt.com/exam/events"

    
        try:
            weather_response = requests.get(weather_url)
            weather_response.raise_for_status()
            weather_data = weather_response.json()

        
            events_response = requests.get(events_url)
            events_response.raise_for_status()
            events_data = events_response.json()

        except requests.exceptions.RequestException as e:
            print('API error: ', e)

    
        
        with open(employee_file_name, 'r') as file:
            employee_data = json.load(file)

        with open(attendance_file_name, 'r') as file:
            attendance_data = json.load(file)
        

        for employee in employee_data:
    
            country = employee['country']
            employee_attendance_data = self.get_employee_attendance_data(employee['record_id'], attendance_data, 2023)
            poor_employee_attendance_data = self.check_employee_times(employee_attendance_data)

            events_cross_reference = self.check_dates_against_events(weather_data, events_data, poor_employee_attendance_data, country)

            average_hours_worked_per_week = self.calculate_average_hours_per_week(employee_attendance_data)
            if len(events_cross_reference) > 3:
                employee_information = {
                    'record_id' : employee['record_id'],
                    'name' : employee['name'],
                    'work_id_number' : employee['work_id_number'],
                    'email_address' : employee['email_address'],
                    'country' : employee['country'],
                    'phone_number' : employee['phone_number'],
                    'average_hours_per_week': average_hours_worked_per_week,
                    'events': events_cross_reference
                }
                wayward_employees.append(employee_information)
        # print(json.dumps(wayward_employees, indent=4))
        return wayward_employees
    

            


    
if __name__ == "__main__":
    AR = AttendanceReport()
    dataset = AR.identify_delinquent_employees("employees.json", "attendance.json")

    file_path = "output.json"

    # List is written to json file 
    with open(file_path, 'w') as json_file:
        json.dump(dataset, json_file, indent=4)










    



