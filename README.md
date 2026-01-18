# NIDD Insights

An interactive web-based tool for generating Unified Modeling Language (UML) diagrams and Parameterized Relation diagram: "Easily uploads structured Excel files and generate clean, well-organized UML class diagrams automatically."

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

---

## 📊 Excel File Format Requirements

### Expected Excel Column Structure

The application expects Excel files with the following column layout:

#### **For Parameter Relations (Parameter Diagram)**:
| Column | Index | Name | Description |
|--------|-------|------|-------------|
| **Column B** | 1 | MOC Name | Managed Object Class name |
| **Column C** | 2 | Parameter Name | Full parameter name |
| **Column D** | 3 | Abbreviation | Short form/abbreviation of parameter |
| **Column E** | 4 | Data Type | Parameter data type |
| **Column F** | 5 | Parent Parameter | Parent parameter reference |
| **Column P** | 15 | Related Parameters | Semicolon-separated list of related abbreviations (format: `ABBR1; ABBR2::public; ABBR3`) |

#### **For UML Diagrams (Additional Columns)**:
| Column | Index | Name | Description |
|--------|-------|------|-------------|
| **Column Z** | 25 | Required On Creation | Whether parameter is required (Mandatory/Optional) |
| **Column AB** | 27 | Required On Creation (Alt) | Alternative required status column |
| **Column AC** | 28 | Modification | Modification type (BTS/On-line/Not modifiable) |
| **Column AD** | 29 | MinOccurs | Minimum occurrences/multiplicity |
| **Column AE** | 30 | MaxOccurs | Maximum occurrences/multiplicity |

### 📝 Important Notes:
- The tool automatically detects header rows by searching for keywords like "Parameter", "Abbreviation", "Relation"
- First 10 rows are checked for headers
- Related parameters in Column P should be separated by semicolons (`;`)
- Format for related parameters: `ABBR::modifier` (e.g., `GPS::public`) - the `::modifier` part is automatically stripped
- Sheets with fewer than 16 columns are skipped

---

## 🔧 Customizing Column Indexes

If your Excel file has a different column structure, you need to modify the column indexes in `main.py`:

### For Parameter Relations:
**Location**: `load_excel_data()` function (approximately **line 162-165**)
```python
# Current mapping (0-indexed):
col_full = df.columns[2]   # Column C - Full Parameter Name
col_abbr = df.columns[3]   # Column D - Abbreviation
col_rel = df.columns[15]   # Column P - Related parameters
```

**To change**: Modify the index numbers (remember Python uses 0-based indexing, so Column A = 0, Column B = 1, etc.)

### For UML Diagrams:
**Location**: `load_uml_data()` function (approximately **line 268-278**)
```python
data = data.rename(columns={
    data.columns[1]: "MOC_Name",                      # Column B
    data.columns[2]: "Parameter_Name",                # Column C
    data.columns[3]: "Abbreviation",                  # Column D
    data.columns[4]: "Data_Type",                     # Column E
    data.columns[5]: "Parent_Parameter",              # Column F
    data.columns[25]: "Required_On_Creation",         # Column Z
    data.columns[27]: "Required_On_Creation_Col_AB",  # Column AB
    data.columns[28]: "Modification",                 # Column AC
    data.columns[29]: "MinOccurs",                    # Column AD
    data.columns[30]: "MaxOccurs"                     # Column AE
})
```

**To change**: Update the column index numbers in square brackets to match your Excel structure.

### For Parameter Relation Detection:
**Location**: `get_relation()` function (approximately **line 382-383**)
```python
col_D = df.columns[3]  # Column D - Abbreviation
col_P = df.columns[15] # Column P - Related parameters
```

### Quick Reference - Column Index Conversion:
```text
Column A = 0    Column N = 13   Column AA = 26
Column B = 1    Column O = 14   Column AB = 27
Column C = 2    Column P = 15   Column AC = 28
Column D = 3    Column Q = 16   Column AD = 29
Column E = 4    Column R = 17   Column AE = 30
...and so on (Column_Number - 1 = Index)
```

---

## Methodology:
we are taking a xl sheet file and analyzing all the data in that file.
Further after analyzing we are creating a uml diagram that shows the relationship between the class and parameters. 
They are also color coded based on the modifications; furthermore they are addressed in a uml diagram that shows the depth of the relation

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