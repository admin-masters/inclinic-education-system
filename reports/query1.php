<?php
// Display all errors for debugging
error_reporting(E_ALL);
ini_set('display_errors', 1);

// Include the database connection configuration
include 'config/constants.php'; // Ensure this contains your DB connection setup

// Check connection
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

// Check if file is uploaded and form is submitted
if ($_SERVER['REQUEST_METHOD'] == 'POST' && isset($_FILES['csv_file'])) {
    $fileName = $_FILES['csv_file']['tmp_name'];

    // Check if the uploaded file has data
    if ($_FILES['csv_file']['size'] > 0) {
        $file = fopen($fileName, 'r');

        // Create an array to store the updated CSV data
        $updatedData = [];

        // Read the first line as header row and append the "Doctor number present" column
        $header = fgetcsv($file);
        $header[] = "Doctor number present"; // Add new column
        $updatedData[] = $header;

        // Loop through each record in the CSV
        while (($row = fgetcsv($file)) !== FALSE) {
            $field_id = $row[0]; // First column: Field ID
            $doctor_name = $row[1]; // Second column: Dr Name (not used in matching but preserved)
            $dr_whatsapp_number = $row[2]; // Third column: Dr Whatsapp Number (10 digit Mobile Number)

            // Prepare a SQL query to fetch matching mobile_number and field_id from 'doctors' table
            $stmt = $conn->prepare("SELECT * FROM doctors WHERE mobile_number = ? AND field_id = ?");
            $stmt->bind_param("ss", $dr_whatsapp_number, $field_id); // Bind parameters safely
            $stmt->execute();
            $result = $stmt->get_result();

            if ($result && $result->num_rows > 0) {
                // If a match is found, mark "Yes" in the "Doctor number present" column
                $row[] = "Yes";
            } else {
                // If no match is found, mark "No"
                $row[] = "No";
            }

            // Add the updated row with the new column to the updated CSV data array
            $updatedData[] = $row;
        }

        fclose($file); // Close the file after reading

        // Output the updated CSV as a downloadable file
        header('Content-Type: text/csv');
        header('Content-Disposition: attachment;filename=updated_data.csv');
        $output = fopen('php://output', 'w');

        // Write each updated row to the CSV output
        foreach ($updatedData as $line) {
            fputcsv($output, $line);
        }

        fclose($output); // Close the output stream

    } else {
        // Handle empty file upload
        echo "The uploaded file is empty!";
    }
} else {
    // Handle case where no file is uploaded
    echo "No file uploaded!";
}

// Close the database connection
$conn->close();
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CSV Upload</title>
</head>
<body>
    <h2>Upload CSV</h2>
    <form action="" method="POST" enctype="multipart/form-data">
        <input type="file" name="csv_file" accept=".csv" required>
        <button type="submit">Upload and Process</button>
    </form>
</body>
</html>
