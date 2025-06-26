import streamlit as st
import pandas as pd
import plotly.express as px
import zipfile
import tempfile
import os
import re
import io

# Blue/Black Theme Configuration
st.set_page_config(
    page_title="GACL FINAL Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="📊"
)

# Custom CSS for Blue/Black Theme
# Custom CSS for Visible Data Type Radio Buttons
st.markdown("""
<style>
    /* [Keep all other existing CSS rules...] */

    /* Data Type Radio Buttons - Dark Text in White Boxes */
    [data-testid="stSidebar"] div[role="radiogroup"] {
        background: white !important;
        border-radius: 10px !important;
        padding: 8px !important;
        margin-top: 8px !important;
        margin-bottom: 16px !important;
    }
    
    /* Radio button labels */
    [data-testid="stSidebar"] div[role="radiogroup"] label {
        color: #1a2a6c !important;  /* Dark blue text */
        font-weight: 600 !important;
        padding: 8px 12px !important;
    }
    
    /* Selected option */
    [data-testid="stSidebar"] div[role="radiogroup"] > div:first-child {
        background: #d1e0ff !important;  /* Light blue highlight */
        border-radius: 8px !important;
    }
    
    /* Radio button circles */
    [data-testid="stSidebar"] div[role="radiogroup"] [role="radio"] {
        border-color: #1a2a6c !important;  /* Dark blue border */
    }
    
    [data-testid="stSidebar"] div[role="radiogroup"] [role="radio"]:after {
        background: #1a2a6c !important;  /* Dark blue fill */
    }
</style>
""", unsafe_allow_html=True)
@st.cache_data(show_spinner="Processing ZIP file...")
def process_zip_and_mapping(zip_file):
    temp_dir = tempfile.mkdtemp()
    with zipfile.ZipFile(zip_file, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)

    # Read mapping files
    material_mapping, capacity_mapping = None, None

    for root, dirs, files in os.walk(temp_dir):
        for file in files:
            if file.lower() == "material_group_mapping.csv":
                material_mapping = pd.read_csv(os.path.join(root, file), dtype=str)
            elif file.lower() == "capacity_mapping.csv":
                capacity_mapping = pd.read_csv(os.path.join(root, file), dtype=str)

    if material_mapping is None or capacity_mapping is None:
        st.error("⚠️ Both mapping files are required inside ZIP!")
        return None, None

    # Clean column names
    material_mapping.columns = material_mapping.columns.str.strip()
    capacity_mapping.columns = capacity_mapping.columns.str.strip()

    # Handle same column name conflict
    if 'Capacity' in capacity_mapping.columns:
        capacity_mapping.rename(columns={'Capacity': 'Capacity (MT/Day)'}, inplace=True)
    if 'Group Name' in capacity_mapping.columns:
        capacity_mapping.rename(columns={'Group Name': 'Capacity Group Name'}, inplace=True)

    # Ensure proper datatypes
    material_mapping['Material Group Code'] = material_mapping['Material Group Code'].astype(str).str.strip()
    material_mapping['Group Name'] = material_mapping['Group Name'].astype(str).str.strip()

    capacity_mapping['Material Group Code'] = capacity_mapping['Material Group Code'].astype(str).str.strip()
    capacity_mapping['Plant'] = capacity_mapping['Plant'].astype(str).str.strip()
    capacity_mapping['Capacity (MT/Day)'] = pd.to_numeric(capacity_mapping['Capacity (MT/Day)'], errors='coerce').fillna(0)

    # Process Sales & Stock Excel files
    sales_data, stock_data = [], []

    for root, dirs, files in os.walk(temp_dir):
        for file in files:
            if not file.lower().endswith('.xlsx') or file.startswith('~$'):
                continue

            filename_clean = re.sub(r'(\.XLSX)+$', '.XLSX', file, flags=re.IGNORECASE)
            match = re.match(r"(.+?)_(Sales_)?(\d{2}-\d{2}-\d{4})\.XLSX", filename_clean, re.IGNORECASE)
            if not match:
                continue

            plant = match.group(1)
            is_sales = 'Sales' if match.group(2) else 'Stock'
            file_date = match.group(3)

            file_path = os.path.join(root, file)
            df = pd.read_excel(file_path, engine='openpyxl')
            df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
            if 'Material Code' not in df.columns:
                continue

            df = df.dropna(subset=['Material Code'])
            df['Material Code'] = df['Material Code'].astype(str).str.strip()
            df['Material Group Code'] = df['Material Code'].str[:6].str.strip()

            if 'Material' in df.columns:
                df['Material'] = df['Material'].ffill()
            else:
                df['Material'] = None

            numeric_cols = ['Today', 'Month', 'Current Year', 'Today External Sale', 'Month Sale', 'Current Year Sale']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            df['Material Code Full Name'] = df['Material Code'] + ' - ' + df['Material']
            df['Plant'] = plant.strip()
            df['DataType'] = is_sales
            df['FileDate'] = pd.to_datetime(file_date, format="%d-%m-%Y")

            if plant.startswith('Brd'):
                df['PlantGroup'] = 'Baroda'
            elif plant.startswith('Coelho'):
                df['PlantGroup'] = 'Cohelco'
            else:
                df['PlantGroup'] = 'Dahej'

            if is_sales == 'Sales':
                sales_data.append(df)
            else:
                stock_data.append(df)

    # Merge mappings
    def merge_data(df):
        if df.empty:
            return df

        df = df.merge(material_mapping, how='left', on='Material Group Code')
        df = df.merge(capacity_mapping, how='left', on=['Material Group Code', 'Plant'])

        df['Group Name'] = df['Group Name'].fillna('Unknown')
        df['Capacity (MT/Day)'] = df['Capacity (MT/Day)'].fillna(0)
        df['Material Group Display'] = df['Material Group Code'] + " - " + df['Group Name']
        return df

    sales_df = merge_data(pd.concat(sales_data, ignore_index=True) if sales_data else pd.DataFrame())
    stock_df = merge_data(pd.concat(stock_data, ignore_index=True) if stock_data else pd.DataFrame())

    return sales_df, stock_df

# Dashboard Header
st.title("📊 GACL DPR Dashboard")
st.markdown("---")

# Sidebar with Upload and Filters
with st.sidebar:
    st.header("📁 Data Upload")
    zip_file = st.file_uploader("Upload ZIP File", type=["zip"])
    
    if zip_file:
        st.markdown("---")
        st.header("🔍 Filters")
        data_type = st.radio("Data Type:", ['Sales', 'Stock'], horizontal=True)

# Main Dashboard Logic
if zip_file:
    sales_df, stock_df = process_zip_and_mapping(zip_file)

    if sales_df is not None and stock_df is not None:
        df = sales_df if data_type == 'Sales' else stock_df

        if df.empty:
            st.warning("⚠️ No data found in the uploaded files")
        else:
            # Create tabs based on data type
            if data_type == 'Sales':
                tabs = st.tabs(["📈 KPIs", "📊 Pie Chart", "📉 Trends", "🗃️ Raw Data"])
            else:
                tabs = st.tabs(["📈 KPIs", "📊 Pie Chart", "📉 Trends", "⚙️ Capacity", "🗃️ Raw Data"])

            # Filters
            with st.sidebar:
                plant_groups = ['All'] + sorted(df['PlantGroup'].dropna().unique())
                selected_plant = st.selectbox("🏭 Plant Group:", plant_groups)
                
                filtered_df = df if selected_plant == 'All' else df[df['PlantGroup'] == selected_plant]
                
                material_groups = ['All'] + sorted(filtered_df['Material Group Display'].dropna().unique())
                selected_group = st.selectbox("📦 Material Group:", material_groups)
                
                if selected_group != 'All':
                    group_code = selected_group.split(' - ')[0]
                    filtered_df = filtered_df[filtered_df['Material Group Code'] == group_code]
                
                min_date, max_date = filtered_df['FileDate'].min(), filtered_df['FileDate'].max()
                date_range = st.date_input("📅 Date Range:", [min_date, max_date])
                filtered_df = filtered_df[
                    (filtered_df['FileDate'] >= pd.to_datetime(date_range[0])) &
                    (filtered_df['FileDate'] <= pd.to_datetime(date_range[1]))
                ]

            # KPIs tab
            with tabs[0]:
                min_date, max_date = df['FileDate'].min(), df['FileDate'].max()
                cols = st.columns(4)
                cols[0].metric("📑 Total Records", len(df))
                cols[1].metric("🏷️ Material Groups", df['Group Name'].nunique())
                cols[2].metric("🏭 Plants", df['Plant'].nunique())
                cols[3].metric("📅 Date Range", f"{min_date.date()} ➔ {max_date.date()}")

            numeric_cols = filtered_df.select_dtypes(include=['number']).columns.tolist()
            metric_cols = []
            if data_type == 'Sales':
                metric_cols = [col for col in numeric_cols if 'Sale' in col]
            else:
                metric_cols = [col for col in numeric_cols if col in ['Today', 'Month', 'Current Year']]

            if metric_cols:
                # Pie Chart tab
                with tabs[1]:
                    selected_metric = st.selectbox("Select Metric:", metric_cols, key="pie_metric")
                    pie_df = filtered_df.groupby('Material Group Display')[selected_metric].sum().reset_index()
                    fig_pie = px.pie(pie_df, names='Material Group Display', values=selected_metric, 
                                   hole=0.3, color_discrete_sequence=px.colors.qualitative.Pastel)
                    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                    fig_pie.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        margin=dict(t=40, b=20, l=20, r=20)
                    )
                    st.plotly_chart(fig_pie, use_container_width=True, key="pie_chart")

                # Trend tab
                with tabs[2]:
                    selected_metric = st.selectbox("Select Metric:", metric_cols, key="trend_metric")
                    trend_df = filtered_df.groupby(['FileDate', 'Plant'])[selected_metric].sum().reset_index()
                    fig_line = px.line(trend_df, x='FileDate', y=selected_metric, color='Plant', markers=True)
                    fig_line.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        hovermode="x unified"
                    )
                    st.plotly_chart(fig_line, use_container_width=True, key="trend_chart")

                if data_type == 'Stock':
                    # Capacity tab
                    with tabs[3]:
                        selected_metric = st.selectbox("Select Metric:", metric_cols, key="capacity_metric")
                        cap_df = filtered_df.groupby(['Material Group Display'])[[selected_metric, 'Capacity (MT/Day)']].sum().reset_index()
                        cap_df['Utilization %'] = (cap_df[selected_metric] / (cap_df['Capacity (MT/Day)'] * len(filtered_df['FileDate'].unique()))) * 100
                        cap_df['Utilization %'] = cap_df['Utilization %'].fillna(0).round(2)

                        for index, row in cap_df.iterrows():
                            with st.container():
                                st.markdown('<div class="gauge-container">', unsafe_allow_html=True)
                                st.subheader(f"{row['Material Group Display']}")
                                utilization = row['Utilization %']

                                if utilization < 60:
                                    color = '#2ecc71'  # Green
                                elif utilization < 90:
                                    color = '#f39c12'  # Orange
                                elif utilization < 110:
                                    color = '#e74c3c'  # Red
                                else:
                                    color = '#9b59b6'  # Purple
                                
                                display_value = f"{utilization}%"
                                if utilization > 100:
                                    display_value += "<br><span style='font-size: 12px; color: #e74c3c;'>Over Capacity</span>"

                                fig_gauge = px.pie(
                                    values=[min(utilization, 100), max(100 - utilization, 0)],
                                    names=["Utilized", "Remaining"],
                                    hole=0.7,
                                    color_discrete_sequence=[color, '#ecf0f1']
                                )
                                
                                fig_gauge.update_traces(
                                    textinfo='none',
                                    rotation=90,
                                    marker=dict(line=dict(color='#ffffff', width=2))
                                )
                                
                                fig_gauge.update_layout(
                                    showlegend=False,
                                    margin=dict(t=0, b=0, l=0, r=0),
                                    annotations=[
                                        dict(
                                            text=display_value, 
                                            x=0.5, y=0.5, 
                                            font_size=28, 
                                            showarrow=False, 
                                            align='center',
                                            font=dict(color=color)
                                        )
                                    ],
                                    height=300,
                                    width=300
                                )
                                
                                unique_key = f"gauge_{row['Material Group Display'].replace(' ', '_')}_{index}"
                                st.plotly_chart(fig_gauge, use_container_width=True, key=unique_key)
                                st.markdown('</div>', unsafe_allow_html=True)

                # Raw Data tab
                with tabs[-1]:
                    selected_metric = st.selectbox("Select Metric:", metric_cols, key="raw_metric")
                    
                    # Summary stats
                    st.subheader("📋 Data Summary")
                    summary_col1, summary_col2, summary_col3 = st.columns(3)
                    summary_col1.metric("Total Records", len(filtered_df))
                    summary_col2.metric("Average Value", round(filtered_df[selected_metric].mean(), 2))
                    summary_col3.metric("Total Value", round(filtered_df[selected_metric].sum(), 2))
                    
                    # Dataframe with styling
                    st.dataframe(
                        filtered_df.style.background_gradient(
                            subset=[selected_metric],
                            cmap='Blues'
                        ),
                        use_container_width=True,
                        height=600
                    )
                    
                    # Download button
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        filtered_df.to_excel(writer, index=False)
                    st.download_button(
                        "💾 Download Filtered Data", 
                        data=output.getvalue(),
                        file_name=f"GACL_{data_type}_Data.xlsx", 
                        mime="application/vnd.ms-excel"
                    )
            else:
                st.warning("⚠️ No numeric columns found for visualization")