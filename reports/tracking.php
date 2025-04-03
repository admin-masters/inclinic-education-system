<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
require 'config/constants.php';


// Check if the brand_campaign_id is set in the URL, if not, use a default value
$brand_campaign_id = isset($_GET['Brand_Campaign_ID']) ? $_GET['Brand_Campaign_ID'] : 'default_id';

// Query to fetch the total count of unique_ids in field_reps for the given brand_campaign_id
$sql_field_reps = "SELECT COUNT(DISTINCT unique_id) as count FROM field_reps WHERE brand_campaign_id='$brand_campaign_id'";
$result_field_reps = $conn->query($sql_field_reps);
$field_reps_count = 0;
if ($result_field_reps->num_rows > 0) {
    $row = $result_field_reps->fetch_assoc();
    $field_reps_count = $row['count'];
}

// Fetch all unique_ids from field_reps for the given brand_campaign_id
$sql_field_reps_ids = "SELECT unique_id FROM field_reps WHERE brand_campaign_id='$brand_campaign_id'";
$result_field_reps_ids = $conn->query($sql_field_reps_ids);
$field_reps_ids = [];
if ($result_field_reps_ids->num_rows > 0) {
    while ($row = $result_field_reps_ids->fetch_assoc()) {
        $field_reps_ids[] = $row['unique_id'];
    }
}

// Convert the array to a string for SQL IN clause
$field_reps_ids_str = implode("','", $field_reps_ids);

// Query to fetch the total count of rows in doctors table based on the fetched unique_ids
$sql_doctors = "SELECT COUNT(*) as count FROM doctors WHERE field_unique_id IN ('$field_reps_ids_str')";
$result_doctors = $conn->query($sql_doctors);
$doctors_count = 0;
if ($result_doctors->num_rows > 0) {
    $row = $result_doctors->fetch_assoc();
    $doctors_count = $row['count'];
}

// Query to fetch the total count of rows in collateral_transactions where pdf_page is not null or empty
$sql_collateral_transactions = "SELECT COUNT(*) as count FROM collateral_transactions WHERE pdf_page IS NOT NULL AND pdf_page != '' AND field_unique_id IN ('$field_reps_ids_str')";
$result_collateral_transactions = $conn->query($sql_collateral_transactions);
$collateral_transactions_count = 0;
if ($result_collateral_transactions->num_rows > 0) {
    $row = $result_collateral_transactions->fetch_assoc();
    $collateral_transactions_count = $row['count'];
}

// Function to get the count of transactions in the last 7 days
function get_last_7_days_count($conn, $field_reps_ids_str, $input_date) {
    $input_date = date('Y-m-d', strtotime($input_date));
    $start_date = date('Y-m-d', strtotime($input_date . ' -7 days'));
    
    $sql_last_7_days = "SELECT COUNT(*) as count FROM collateral_transactions 
                        WHERE pdf_page IS NOT NULL AND pdf_page != '' 
                        AND field_unique_id IN ('$field_reps_ids_str')
                        AND transaction_date BETWEEN '$start_date' AND '$input_date'";
    $result_last_7_days = $conn->query($sql_last_7_days);
    $last_7_days_count = 0;
    if ($result_last_7_days->num_rows > 0) {
        $row = $result_last_7_days->fetch_assoc();
        $last_7_days_count = $row['count'];
    }
    return $last_7_days_count;
}

// Function to get the sum of pdf_download in the last 7 days
function get_last_7_days_download($conn, $field_reps_ids_str, $input_date) {
    $input_date = date('Y-m-d', strtotime($input_date));
    $start_date = date('Y-m-d', strtotime($input_date . ' -7 days'));
    
    $sql_last_7_days_download = "SELECT SUM(pdf_download) as sum FROM collateral_transactions 
                                 WHERE field_unique_id IN ('$field_reps_ids_str')
                                 AND transaction_date BETWEEN '$start_date' AND '$input_date'";
    $result_last_7_days_download = $conn->query($sql_last_7_days_download);
    $last_7_days_download = 0;
    if ($result_last_7_days_download->num_rows > 0) {
        $row = $result_last_7_days_download->fetch_assoc();
        $last_7_days_download = $row['sum'];
    }
    return $last_7_days_download;
}

// Function to get the cumulative sum of pdf_download
function get_cumulative_download($conn, $field_reps_ids_str) {
    $sql_cumulative_download = "SELECT SUM(pdf_download) as sum FROM collateral_transactions 
                                WHERE field_unique_id IN ('$field_reps_ids_str')";
    $result_cumulative_download = $conn->query($sql_cumulative_download);
    $cumulative_download = 0;
    if ($result_cumulative_download->num_rows > 0) {
        $row = $result_cumulative_download->fetch_assoc();
        $cumulative_download = $row['sum'];
    }
    return $cumulative_download;
}

// Function to get the count of video views based on watch time percentage for the last 7 days
function get_last_7_days_video_views_count($conn, $field_reps_ids_str, $watch_time_percentage, $input_date) {
    $input_date = date('Y-m-d', strtotime($input_date));
    $start_date = date('Y-m-d', strtotime($input_date . ' -7 days'));
    
    $sql_video_views = "SELECT COUNT(*) as count FROM collateral_transactions 
                        WHERE video_pec = '$watch_time_percentage' 
                        AND field_unique_id IN ('$field_reps_ids_str')
                        AND transaction_date BETWEEN '$start_date' AND '$input_date'";
    $result_video_views = $conn->query($sql_video_views);
    $video_views_count = 0;
    if ($result_video_views->num_rows > 0) {
        $row = $result_video_views->fetch_assoc();
        $video_views_count = $row['count'];
    }
    return $video_views_count;
}

// Function to get the cumulative count of video views based on watch time percentage
function get_cumulative_video_views_count($conn, $field_reps_ids_str, $watch_time_percentage) {
    $sql_video_views = "SELECT COUNT(*) as count FROM collateral_transactions 
                        WHERE video_pec = '$watch_time_percentage' 
                        AND field_unique_id IN ('$field_reps_ids_str')";
    $result_video_views = $conn->query($sql_video_views);
    $video_views_count = 0;
    if ($result_video_views->num_rows > 0) {
        $row = $result_video_views->fetch_assoc();
        $video_views_count = $row['count'];
    }
    return $video_views_count;
}

// Check if date is set in POST request
$last_7_days_count = 0;
$last_7_days_download = 0;
$cumulative_download = get_cumulative_download($conn, $field_reps_ids_str);
$last_7_days_video_views_less_50 = 0;
$last_7_days_video_views_more_50 = 0;
$last_7_days_video_views_100 = 0;
$cumulative_video_views_less_50 = 0;
$cumulative_video_views_more_50 = 0;
$cumulative_video_views_100 = 0;

if (isset($_POST['date'])) {
    $input_date = $_POST['date'];
    $last_7_days_count = get_last_7_days_count($conn, $field_reps_ids_str, $input_date);
    $last_7_days_download = get_last_7_days_download($conn, $field_reps_ids_str, $input_date);
    $last_7_days_video_views_less_50 = get_last_7_days_video_views_count($conn, $field_reps_ids_str, 1, $input_date);
    $last_7_days_video_views_more_50 = get_last_7_days_video_views_count($conn, $field_reps_ids_str, 2, $input_date);
    $last_7_days_video_views_100 = get_last_7_days_video_views_count($conn, $field_reps_ids_str, 3, $input_date);
}

$cumulative_video_views_less_50 = get_cumulative_video_views_count($conn, $field_reps_ids_str, 1);
$cumulative_video_views_more_50 = get_cumulative_video_views_count($conn, $field_reps_ids_str, 2);
$cumulative_video_views_100 = get_cumulative_video_views_count($conn, $field_reps_ids_str, 3);

$conn->close();
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Doctor Registration and Collateral Report</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f4f4f4;
        }
        .container {
            width: 90%;
            margin: auto;
            overflow: hidden;
        }
        h1, h2 {
            text-align: center;
            color: #333;
        }
        form {
            background: #fff;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
            max-width: 100%;
        }
        form label {
            display: block;
            margin-bottom: 10px;
            font-weight: bold;
        }
        form input[type="date"] {
            width: 95%;
            padding: 10px;
            margin-bottom: 20px;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
        form input[type="submit"] {
            display: block;
            width: 95%;
            padding: 10px;
            background: #333;
            color: #fff;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        form input[type="submit"]:hover {
            background: #555;
        }
        table {
            width: 100%;
            margin-bottom: 20px;
            border-collapse: collapse;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
        }
        table, th, td {
            border: 1px solid #ccc;
        }
        th, td {
            padding: 12px;
            text-align: center;
            background: #fff;
            font-size: 25px;
        }
        th {
            background: #333;
            color: #fff;
        }
        @media (max-width: 768px) {
            table, th, td {
                font-size: 18px;
            }
        }
        @media (max-width: 480px) {
            form, table {
                width: 100%;
                padding: 10px;
            }
            form input[type="date"] {
                width: 90%;
            }
            form input[type="submit"] {
                width: 90%;
            }
            th, td {
                font-size: 16px;
            }
        }
        @media (max-width: 360px) {
            form, table {
                width: 100%;
                padding: 10px;
            }
            form input[type="date"] {
                width: 90%;
            }
            form input[type="submit"] {
                width: 90%;
            }
            th, td {
                font-size: 16px;
            }
        }
    </style>

</head>
<body>
    <div class="container">
        <h1>Doctor Registration and Collateral Report</h1>

        <form action="?Brand_Campaign_ID=<?php echo $brand_campaign_id; ?>" method="POST">
            <label for="date">Select Date:</label>
            <input type="date" id="date" name="date" required>
            <p>Selected Date is <?php echo isset($input_date) ? $input_date : ''; ?></p>
            <input type="submit" value="Generate Report">
        </form>

        <h2>Number of field reps AND doctors registered under this brand</h2>
        <table>
            <tr>
                <th>Field Reps</th>
                <th>Total Doctors</th>
            </tr>
            <tr>
                <td data-label="Field Reps"><?php echo $field_reps_count; ?></td>
                <td data-label="Total Doctors"><?php echo $doctors_count; ?></td>
            </tr>
        </table>

        <h2>Number of doctors who have viewed the last page of PDF</h2>
        <table>
            <tr>
                <th>Last 7 Days</th>
                <th>Cumulative</th>
            </tr>
            <tr>
                <td data-label="Last 7 Days"><?php echo $last_7_days_count; ?></td>
                <td data-label="Cumulative"><?php echo $collateral_transactions_count; ?></td>
            </tr>
        </table>

        <h2>Number of doctors who have downloaded the PDF</h2>
        <table>
            <tr>
                <th>Last 7 Days</th>
                <th>Cumulative</th>
            </tr>
            <tr>
                <td data-label="Last 7 Days"><?php echo $last_7_days_download; ?></td>
                <td data-label="Cumulative"><?php echo $cumulative_download; ?></td>
            </tr>
        </table>

        <h2>Number of doctors who have watched the video</h2>
        <table>
            <tr>
                <th>percentage of total watch time</th>
                <th>Last 7 Days (Count)</th>
                <th>Cumulative (Count)</th>
            </tr>
            <tr>
                <td data-label="percentage of total watch time">Less than 50%</td>
                <td data-label="Last 7 Days (Count)"><?php echo $last_7_days_video_views_less_50; ?></td>
                <td data-label="Cumulative (Count)"><?php echo $cumulative_video_views_less_50; ?></td>
            </tr>
            <tr>
                <td data-label="percentage of total watch time">More than 50%</td>
                <td data-label="Last 7 Days (Count)"><?php echo $last_7_days_video_views_more_50; ?></td>
                <td data-label="Cumulative (Count)"><?php echo $cumulative_video_views_more_50; ?></td>
            </tr>
            <tr>
                <td data-label="percentage of total watch time">100%</td>
                <td data-label="Last 7 Days (Count)"><?php echo $last_7_days_video_views_100; ?></td>
                <td data-label="Cumulative (Count)"><?php echo $cumulative_video_views_100; ?></td>
            </tr>
        </table>
    </div>
</body>
</html>
