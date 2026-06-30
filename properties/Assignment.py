# Team members:
#  1. Carlos Mutembei Mutembei
# 2. Sandra Mwimali
# 3. John Mwaura
# 4. Paul Kamau

# Initial dataset with 5 sports team members
team_members = [
    {"id": 1, "name": "James Mwangi", "position": "Goalkeeper", "age": 24},
    {"id": 2, "name": "Peter Otieno", "position": "Defender", "age": 22},
    {"id": 3, "name": "Samuel Kamau", "position": "Midfielder", "age": 21},
    {"id": 4, "name": "David Njoroge", "position": "Striker", "age": 23},
    {"id": 5, "name": "Brian Ochieng", "position": "Winger", "age": 20}
]
# Function to display team members
def display_members(members):
    print(f"\n-----------Displaying {len(members)} Team Members-----------\n")
    for member in members:
        print(f"ID: {member['id']}, Name: {member['name']}, Position: {member['position']}, Age: {member['age']} ")
display_members(team_members)

# Function to add a new member to the team
def add_member(members, new_member, name, position, age):
    new_id = max(member['id'] for member in members) + 1
    new_member['id'] = new_id
    new_member['name'] = name
    new_member['position'] = position
    new_member['age'] = age
    members.append(new_member)
    
# Example of adding a new member
new_member = {}
name = input("Enter the name of the new member: ")
position = input("Enter the position of the new member: ")
age = int(input("Enter the age of the new member: "))
add_member(team_members, new_member, name, position, age)
display_members(team_members)

# Total number of records in our dataset
print('\n---------Calculating Total Records---------\n')
def total_records(members):
    return len(members)
print(f"Total number of team members: {total_records(team_members)}")
print('\n------------------------------------------\n')

# Task 3: Explain Your Design Decisions
# We selected the sports team members context because it is practical, relatable, and easy to visualize. 
# Sports clubs constantly manage player details such as names, positions, and ages, so this scenario reflects a real world need for organized record keeping. 
# It also makes the program engaging and straightforward for us all.
# The chosen data structure is a list of dictionaries in Python that we had previously learnt. 
# Each dictionary represents one player with fields (id, name, position, age), while the list stores all records together. 
# This design is appropriate because dictionaries allow clear labeling of attributes, making the data readable and easy to manipulate. 
# The list provides ordered storage and supports dynamic operations such as adding, displaying, and counting records. 
# Together, they balance simplicity and flexibility, which is ideal for demonstrating computational thinking and programming concepts in data science.
# Task 4: Reflection and Improvement
# 1.	Challenge: How do add automated player ID.
# 2.	Solution: We figured it out all together and we managed to solve that challenge by using max( ) function and increment the ID by 1
# Task 4: Reflection (1 Mark)
# 1.	Challenge: Deciding how to structure records clearly.
# 2.	Solution: I switched from nested lists to dictionaries inside a list, which made the data easier to understand and extend. 
# Future improvements could include search or update functions.
# Task 5: AI Use Declaration (1 Mark)
# We did not use AI because the question was a bit simple to do
