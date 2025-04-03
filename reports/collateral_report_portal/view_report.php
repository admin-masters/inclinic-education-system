<?php
session_start(); // Make sure to start the session

include '../server/brands.php'; // Connection file

// Check if the user is logged in
if (!isset($_SESSION['username'])) {
    // If not, redirect to login page
    header("Location: loginpage.php");
    exit();
}

// Get the brand_campaign_id from the URL parameter
$brand_campaign_id = $_GET['brand_campaign_id'];

// Fetch start_date and end_date from brand_campaigns
$campaign_query = "SELECT start_date, end_date FROM brand_campaigns WHERE brand_campaign_id = ?";
$stmt = $conn->prepare($campaign_query);
$stmt->bind_param("s", $brand_campaign_id);
$stmt->execute();
$campaign_result = $stmt->get_result();

if ($campaign_result && $campaign_result->num_rows > 0) {
    $campaign_data = $campaign_result->fetch_assoc();
    // Create DateTime objects
    $start_date = new DateTime($campaign_data['start_date'], new DateTimeZone('Asia/Kolkata'));
    $end_date = new DateTime($campaign_data['end_date'], new DateTimeZone('Asia/Kolkata'));
} else {
    die("Campaign not found.");
}

// Generate dates from start_date to the current date
$current_date = new DateTime('now', new DateTimeZone('Asia/Kolkata'));
$dates = [];
$reports = [];

// Ensure $current_date is at the end of the day
$current_date->setTime(23, 59, 59);

// Populate the dates array
$interval = new DateInterval('P1D'); // 1 day interval
$period = new DatePeriod($start_date, $interval, $current_date);
foreach ($period as $date) {
    $dates[] = $date->format('Y-m-d');
}

// Example report availability (this should be replaced with actual report checks)
foreach ($dates as $date) {
    $reports[$date] = true; // Replace with actual logic to check if reports exist
}

// Close the database connection
$stmt->close();
mysqli_close($conn);
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>View Report</title>
    <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-5">
        <h2>Report for Brand Campaign ID: <?php echo htmlspecialchars($brand_campaign_id); ?></h2>
        <div class="table-responsive">
            <table class="table table-bordered table-striped">
                <thead class="thead-dark">
                    <tr>
                        <th>Dates</th>
                        <th>PDF</th>
                        <th>Excel</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (!empty($dates)): ?>
                        <?php foreach ($dates as $date): ?>
                            <tr>
                                <td><?php echo htmlspecialchars($date); ?></td>
                                <td>
                                    <?php if (isset($reports[$date])): ?>
                                        <a href="generate_pdf.php?brand_campaign_id=<?php echo htmlspecialchars($brand_campaign_id); ?>&date=<?php echo htmlspecialchars($date); ?>" class="btn btn-primary">View PDF</a>
                                    <?php else: ?>
                                        No Report
                                    <?php endif; ?>
                                </td>
                                <td>
                                    <?php if (isset($reports[$date])): ?>
                                        <a href="generate_csv.php?brand_campaign_id=<?php echo htmlspecialchars($brand_campaign_id); ?>&date=<?php echo htmlspecialchars($date); ?>" class="btn btn-primary">View Excel</a>
                                    <?php else: ?>
                                        No Report
                                    <?php endif; ?>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    <?php else: ?>
                        <tr>
                            <td colspan="3">No dates available.</td>
                        </tr>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.5.1.slim.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/@popperjs/core@2.5.2/dist/umd/popper.min.js"></script>
    <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/js/bootstrap.min.js"></script>
</body>
</html>
