import pandas as pd 
from datetime import datetime, timedelta, time
import json
import requests

class AttendanceReport:

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

    def get_employee_attendance_data(self, df, record_id, year):
        '''
            Helper method to filter the rows of the attendance dataframe and return those that 
            belong to the specified employee for the specified year 
        '''
        df['date'] = pd.to_datetime(df['date'])
        return df[(df['employee_record_id'] == record_id) & (df['date'].dt.year == year)]


    def check_employee_times(self, df):
        '''
            Helper method which browses the dataframe and picks out the rows that show the employee
            clocked in late or clocked out early as well as the rows which show absence. A concatenated dataframe
            is returned.
        '''
        df['clock_in'] = pd.to_datetime(df['clock_in'], format='%H:%M:%S').dt.time
        df['clock_out'] = pd.to_datetime(df['clock_out'], format='%H:%M:%S').dt.time

        clock_in_threshold = pd.to_datetime('08:15:00', format='%H:%M:%S').time()
        clock_out_threshold = pd.to_datetime('16:00:00', format='%H:%M:%S').time()

        delinquent_days = df[(df['clock_in'] > clock_in_threshold) | (df['clock_out'] < clock_out_threshold)]
        absent_days = df[df['clock_in'].isna() | df['clock_out'].isna()]

        return pd.concat([delinquent_days, absent_days], ignore_index=True)
    
    def check_dates_against_events(self, weather_df, events_df, attendance_df, country):
        '''
            Helper method which takes in the weather, poor attendance and events dataframes and firstly filters out the 
            days the employee missed due to bad weather in their country. It then checks the remaining days against events in that country.
            If an event occurred on, before or after the delinquent date, then the event name, date and country is records and returned in a list.
        '''
        bad_weather_conditions = ['hail', 'thunderstorm', 'blizzard', 'hurricane']
        filtered_weather_df = weather_df[(weather_df['country'] == country) & ((weather_df['condition'].isin(bad_weather_conditions)) | (weather_df['max_temp'] > 40))]
        common_dates = set(attendance_df['date']).intersection(set(filtered_weather_df['date']))
        attendance_df = attendance_df[~attendance_df['date'].isin(common_dates)]


        events_df['event_date'] = pd.to_datetime(events_df['event_date'])
        filtered_events_df = events_df[(events_df['country'] == country) & (events_df['event_date'].dt.year == 2023)]
        filtered_events_df['event_date'] = pd.to_datetime(filtered_events_df['event_date'])
        event_info = []
        for _, attendance_row in attendance_df.iterrows():
            attendance_date = attendance_row['date']
            date_range = pd.date_range(attendance_date - timedelta(days=1), attendance_date + timedelta(days=1))
            event_reason = filtered_events_df[filtered_events_df['event_date'].isin(date_range)]
            if not event_reason.empty:
                for _, event_reason_row in event_reason.iterrows():
                    event_date = event_reason_row['event_date'].strftime('%Y.%m.%d')

                    event_reason_dict = {
                        'event_date': event_date,
                        'event_name': event_reason_row['event_name'],
                        'country': country
                    }
                    event_info.append(event_reason_dict)
                


        # print(json.dumps(event_info, indent=4))
        event_info = self.remove_duplicate_events(event_info)
        return event_info    

    def calculate_average_hours_per_week(self, attendance_df):
        '''
            Uses the dataframe to calculate the average hours worked per week. First it gets the duration for each day,
            filling in 0s for days abent, then it gets the week number and stores it in the dataframe.
            It uses the week number to group the rows and sum each grouping. The average is then found and returned
        '''
        pd.options.mode.copy_on_write = True

        attendance_df['date'] = pd.to_datetime(attendance_df['date'])
        attendance_df['clock_in'] = pd.to_datetime(attendance_df['clock_in'], format='%H:%M:%S')
        attendance_df['clock_out'] = pd.to_datetime(attendance_df['clock_out'], format='%H:%M:%S')

        attendance_df['duration'] = (attendance_df['clock_out'] - attendance_df['clock_in']).dt.total_seconds() / 3600

        attendance_df['duration'] = attendance_df['duration'].fillna(0)

        attendance_df['week_number'] = attendance_df['date'].dt.isocalendar().week

        weekly_hours = attendance_df.groupby('week_number')['duration'].sum()

        average_hours_per_week = weekly_hours.mean()

        return average_hours_per_week
    




    def analyze_data(self, employee_file_name, attendance_file_name):

        with open(employee_file_name, 'r') as file:
            employee_data = json.load(file)

        attendance_df = pd.read_json(attendance_file_name)

        weather_url = "https://www.pingtt.com/exam/weather"
        events_url = "https://www.pingtt.com/exam/events"

    
        try:
            weather_response = requests.get(weather_url)
            weather_response.raise_for_status()
            weather_data = weather_response.json()
            weather_df = pd.DataFrame(weather_data)

        
            events_response = requests.get(events_url)
            events_response.raise_for_status()
            events_data = events_response.json()
            events_df = pd.DataFrame(events_data)

        except requests.exceptions.RequestException as e:
            print('API error: ', e)

        wayward_employees = []

        for employee in employee_data:
            country = employee['country']
            emp_attendance_df = self.get_employee_attendance_data(attendance_df, employee['record_id'], 2023)
            poor_employee_attendance_df = self.check_employee_times(emp_attendance_df)
            events_cross_reference = self.check_dates_against_events(weather_df, events_df, poor_employee_attendance_df, country)

            average_hours_per_week = self.calculate_average_hours_per_week(emp_attendance_df)

            if len(events_cross_reference) > 3:
                employee_information = {
                    'record_id' : employee['record_id'],
                    'name' : employee['name'],
                    'work_id_number' : employee['work_id_number'],
                    'email_address' : employee['email_address'],
                    'country' : employee['country'],
                    'phone_number' : employee['phone_number'],
                    'average_hours_per_week': average_hours_per_week,
                    'events': events_cross_reference
                }
                wayward_employees.append(employee_information)
            
        return wayward_employees




    

if __name__ == "__main__":
    AR = AttendanceReport()
    dataset = AR.analyze_data("employees.json", "attendance.json")

    file_path = "output_alternate.json"

    # List is written to json file 
    with open(file_path, 'w') as json_file:
        json.dump(dataset, json_file, indent=4)
    

