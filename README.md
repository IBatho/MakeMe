# MakeMe
This is a scheduling app to plan what someone is doing and when and will put such things in thier respective calender.
Capabilities:
- Information will be gathered from APIs such as notion to get dates and times for preplanned events such as lectures. Activities will be listed as need (can't be moved), want (need to do in given time fram but time block(s) can be moved to fit into schedule), and like (fit in when their's room)
- Tasks will be found using an API such as notion to know what activities to add to the callender and for how long. E.g. the task may be to study for 2 hours each week which can be done in time blocks of 30 - 90 minutes.
- This will run on phones and recieve real time updates such as an activity is started and stopped as well as if it was completed in that time or not and if possible a percentage of the task complete. Location data will also be tracked to know how long someone takes to travel between places to know how long to schedule travelling between events
- This information will be used to train a personal AI scheduling agent to schedule tasks and change the schedule if plans change.
- The agent will make a decision and create new events as well as change or delete existing events on the callender by accessing the API
- This will not be a pretrained model it will continuously learn in real time
- It should recognise repeatable patterns and make a schedule to make the best use of the users time while getting the tasks that need to be done complete