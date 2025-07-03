import os
import json
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, send_file
from datetime import datetime
import io

app = Flask(__name__)

# --- Configuration & Helper Functions ---
DATA_FILE = 'packing_data.json'

def load_data():
    """Loads packing data from the JSON file."""
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_data(data):
    """Saves packing data to the JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """Main page to display and create boxes."""
    data = load_data()
    if request.method == 'POST':
        box_name = request.form['box_name'].strip()
        if box_name and box_name not in data:
            data[box_name] = []
            save_data(data)
        return redirect(url_for('index'))
    
    sorted_box_names = sorted(data.keys(), key=lambda x: int(''.join(filter(str.isdigit, x))) if any(char.isdigit() for char in x) else float('inf'))
    
    boxes_with_counts = []
    for box_name in sorted_box_names:
        item_count = len(data[box_name])
        boxes_with_counts.append({'name': box_name, 'count': item_count})
    
    return render_template('index.html', boxes=boxes_with_counts)

@app.route('/box/<box_name>', methods=['GET', 'POST'])
def view_box(box_name):
    """Page to view and add items to a specific box."""
    data = load_data()
    if box_name not in data:
        return redirect(url_for('index'))

    if request.method == 'POST':
        item = request.form['item']
        description = request.form['description']
        qty = int(request.form['quantity'])
        
        if item and description and qty > 0:
            data[box_name].append({'item': item, 'description': description, 'quantity': qty})
            save_data(data)
        return redirect(url_for('view_box', box_name=box_name))

    return render_template('box_view.html', box_name=box_name, items=data[box_name])

# NEW: Route to edit an existing item
@app.route('/edit/<box_name>/<int:item_index>', methods=['GET', 'POST'])
def edit_item(box_name, item_index):
    """Handles editing of a single item."""
    data = load_data()
    if box_name not in data or not 0 <= item_index < len(data[box_name]):
        return redirect(url_for('index'))
    
    item_to_edit = data[box_name][item_index]

    if request.method == 'POST':
        # Update the item with form data
        item_to_edit['item'] = request.form['item']
        item_to_edit['description'] = request.form['description']
        item_to_edit['quantity'] = int(request.form['quantity'])
        save_data(data)
        return redirect(url_for('view_box', box_name=box_name))

    # For a GET request, show the edit form
    return render_template('edit_item.html', box_name=box_name, item_index=item_index, item=item_to_edit)


@app.route('/delete/<box_name>/<int:item_index>')
def delete_item(box_name, item_index):
    """Deletes an item from a box."""
    data = load_data()
    if box_name in data and 0 <= item_index < len(data[box_name]):
        del data[box_name][item_index]
        save_data(data)
    return redirect(url_for('view_box', box_name=box_name))

@app.route('/delete_box/<box_name>')
def delete_box(box_name):
    """Deletes an entire box."""
    data = load_data()
    if box_name in data:
        del data[box_name]
        save_data(data)
    return redirect(url_for('index'))


@app.route('/export/<box_name>')
def export_box(box_name):
    """Exports a box's inventory to an Excel file."""
    data = load_data()
    items = data.get(box_name, [])
    
    if not items:
        return redirect(url_for('view_box', box_name=box_name))

    df = pd.DataFrame(items)
    df = df[['item', 'description', 'quantity']] 
    df.columns = ['ITEM', 'DESCRIPTION', 'SHIPPED QTY'] 

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        ws = writer.book.create_sheet(title="PACKING SLIP")
        
        ws.merge_cells('D1:F1')
        ws['D1'] = 'PACKING SLIP'
        ws['F2'] = 'DATE'
        ws['G2'] = datetime.now().strftime('%d/%m/%Y')
        
        ws['B4'] = 'SHIPPED FROM:'
        ws['B5'] = 'John Doe'
        ws['B6'] = 'Apartment 802, Satin House'
        ws['B7'] = '7 Fresco Walk'
        ws['B8'] = 'London'
        ws['B9'] = 'United Kingdom'
        ws['B10'] = 'E1 8PW'
        
        ws['D4'] = 'SHIP TO:'
        ws['D5'] = 'John Doe'
        ws['D6'] = 'Jl. Pantai Batu Bolong,'
        ws['D7'] = 'Gg. Bantan No.11C'
        ws['D8'] = 'Badung, Bali'
        ws['D9'] = 'Kuta Utara'
        ws['D10'] = '80361'

        start_row = 12 
        df.to_excel(writer, sheet_name='PACKING SLIP', startrow=start_row, index=False)
        
        total_qty = df['SHIPPED QTY'].sum()
        total_row = start_row + len(df) + 2
        ws[f'F{total_row}'] = 'TOTAL:'
        ws[f'G{total_row}'] = total_qty
        
        ws[f'F{total_row+1}'] = 'Total weight:'
        ws[f'G{total_row+1}'] = '12.20 kg' 

        if 'Sheet1' in writer.book.sheetnames:
            writer.book.remove(writer.book['Sheet1'])

    output.seek(0)
    
    return send_file(
        output,
        as_attachment=True,
        download_name=f'{box_name}_Packing_List.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)