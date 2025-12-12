# NIDD Insights

An interactive web-based tool for generating Unified Modeling Language (UML) diagrams and Paremeterized Relation diagram: "Easily uploads structured Excel files and generate clean, well-organized UML class diagrams automatically."

---

## Aim:

-  Upload Excel files containing class definitions
-  Automatically parse class names, attributes, and methods
-  Render clean UML Class Diagrams, Parameterized Diagram
-  Lightweight, fast, and responsive
-  No data is uploaded all processing happens locally in the browser

---

##  Tech Stack

- **Frontend**:
- HTML, CSS, JavaScript
- **Backend**:
- Python, Flask and their related libraries, Pandas, Os Library, and Openpyxl Libraries ,ReportLab library.
- SheetJS library:for reading Excel files

---

### ⚙️ Prerequisites & Run Instructions
Install all the required Libraries
```bash
# Check for updated Python Version, else download the latest version:
python --version

# Download The Python Libraries:
pip install flask pandas openpyxl werkzeug reportlab

# Run the command in Command prompt (Cmd) Terminal:
python main.py

```

## 📁 Folder Structure

```text
UML
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

### Landing page:

<img width="2842" height="1490" alt="landingpage" src="https://github.com/user-attachments/assets/72dec43d-ea2e-4b5a-9eb8-660a659379a2" />

<br><br>
### UML Diagram Page:
<img width="2870" height="1526" alt="umldiagram" src="https://github.com/user-attachments/assets/122c53da-268e-476b-bd11-aecea1f4c939" />

<br><br>
### Parametrized Relation Page:
<br><br>
<img width="2844" height="1516" alt="parameter" src="https://github.com/user-attachments/assets/bd0d1f3d-d915-4ef3-a16d-b8ef7635f75a" />

<br><br>



###  Team:


```text
Pratheeksha Karanth : pratheeksha.ec22@bmsce.ac.in
Pushpa Kumari Pandey : pushpa.ec22@bmsce.ac.in
Sanidhya Sharma : sanidhya.ec22@bmsce.ac.in
Manjari Verma : manjari.ec22@bmsce.ac.in

```
