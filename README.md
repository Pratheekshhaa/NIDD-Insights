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
├── parameter.py
├── tempCodeRunnerFile.py


```
## Methodology:
we are taking a xl sheet file and analyzing all the data in that file.
Further after analyzing we are creating a uml diagram that shows the relationship between the class and parameters. 
They are also color coded based on the modifications; furthermore they are addressed in a uml diagram that shows the depth of the relation

---


---



## Output:

## Landing page:

<img width="1919" height="945" alt="Image" src="https://github.com/user-attachments/assets/95a4b5f9-f9a7-4cb6-92b3-eff68dc44f99" />
<br><br>
<img width="1918" height="941" alt="Screenshot 2025-10-06 155532" src="https://github.com/user-attachments/assets/8ed704ee-0b2c-406b-8713-372377ae349c" />

<br><br>
## UML Diagram Page:

<img width="1915" height="942" alt="Image" src="https://github.com/user-attachments/assets/9fb19bfe-1fb6-4868-96c8-f4c9d5bf5e82" />
<br><br>
<img width="1918" height="941" alt="Image" src="https://github.com/user-attachments/assets/bc76e9bd-23a1-4fb4-bdc2-53df964526b8" />
<br><br>
<img width="1919" height="942" alt="Image" src="https://github.com/user-attachments/assets/5c8232d1-b0aa-4ec1-a415-477a7896e7b7" />
<br><br>
## Parametrized Relation Page:
<br><br>
<img width="1919" height="945" alt="Image" src="https://github.com/user-attachments/assets/dd859f19-a34a-47f4-b72a-84116689ae2c" />
<br><br>
<img width="1913" height="944" alt="Image" src="https://github.com/user-attachments/assets/ddf9415f-706a-4922-9c8a-4a0669ec0dfb" />
<br><br>
<img width="1919" height="948" alt="Image" src="https://github.com/user-attachments/assets/07305829-1174-4156-934c-6c9323be2308" />
<br><br>



###  Team:


```text
Pratheeksha Karanth : pratheeksha.ec22@bmsce.ac.in
Pushpa Kumari Pandey : pushpa.ec22@bmsce.ac.in
Sanidhya Sharma : sanidhya.ec22@bmsce.ac.in
Manjari Verma : manjari.ec22@bmsce.ac.in

```
