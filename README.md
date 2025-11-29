# NIDD Insights

An interactive web-based tool for generating Unified Modeling Language (UML) diagrams and Paremeterized Relation diagram: "Easily uploads structured Excel files and generate clean, well-organized UML class diagrams automatically."

---

## Aim:

-  Upload Excel files containing class definitions
-  Automatically parse class names, attributes, and methods
-  Render clean UML Class Diagrams, Parameterized Diagram
-  Lightweight, fast, and responsive
-  No data is uploaded — all processing happens locally in the browser

---

##  Tech Stack

- **Frontend**:
- HTML, CSS, JavaScript
- **Backend**:
- Python, Flask and their related libraries, Pandas, Watch dog and their related libraries , Os Library, and Openpyxl Libraries .
- SheetJS library:for reading Excel files

---

### ⚙️ Prerequisites & Run Instructions
Install all the required Libraries
```bash
# Check for updated Python Version, else download the latest version:
python --version

# Download The Python Libraries:
pip install flask pandas openpyxl

# Run the command in Command prompt (Cmd) Terminal:
python main.py

```

## 📁 Folder Structure

```text
Nokia_UML
├── templates
│   └── main.html
│   └── parameter.html
│   └── umldiaram.html
├── uploads
│   └── Book1.xlsx
├── main.py


```
## Methodology:
we are taking a xl sheet file and analyzing all the data in that file.
Further after analyzing we are creating a uml diagram that shows the relationship between the class and parameters. 
They are also color coded based on the modifications; furthermore they are addressed in a uml diagram that shows the depth of the relation

---


---



## Output:

## Landing page:

<img width="1920" height="1080" alt="Image" src="https://github.com/user-attachments/assets/7ecf289e-0ce4-4d2d-9f20-e22314d910cc" />
<br><br>
<img width="1920" height="1080" alt="Image" src="https://github.com/user-attachments/assets/4d78bd3a-9e20-44b3-8437-ec2db634d372" />

<br><br>
## UML Diagram Page:

<img width="1920" height="1080" alt="Image" src="https://github.com/user-attachments/assets/089465f3-8cf2-46e7-b634-96a129762c66" />
<br><br>
## Parametrized Relation Page:
<br><br>
<img width="1920" height="1080" alt="Screenshot (126)" src="https://github.com/user-attachments/assets/b9f59448-cfd7-41fd-bf6a-4bdfb184bc9f" />

<br><br>



###  Team:


```text
Pratheeksha Karanth : pratheeksha.ec22@bmsce.ac.in
Pushpa Kumari Pandey : pushpa.ec22@bmsce.ac.in
Sanidhya Sharma : sanidhya.ec22@bmsce.ac.in
Manjari Verma : manjari.ec22@bmsce.ac.in

```
