<!DOCTYPE html>
<html>
<head>
    <title>Doctor Registration Search</title>
    <style>
        body {
            font-family: Arial, sans-serif;
        }
        .report-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        .report-table th, .report-table td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: center;
        }
        .report-table th {
            background-color: #f2f2f2;
            font-weight: bold;
        }
        .report-header {
            background-color: #f9f9f9;
            font-weight: bold;
            text-align: center;
        }
        .report-title {
            text-align: center;
            margin: 20px 0;
            font-size: 24px;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <?php
    // ini_set('display_errors', 1);
    // ini_set('display_startup_errors', 1);
    // error_reporting(E_ALL);
    ?>

    <div class="report-title">Equipoise Report</div>
    <form method="post" action="">
        <label for="date">Enter Date:</label>
        <input type="date" id="date" name="date" required>
        <input type="submit" name="submit" value="Search">
    </form>

    <?php
    include "config/constants.php";
    include "config/forms_db.php";

    function startsWithInditech($name) {
        return strpos(trim($name), 'Inditech') === 0;
    }

    if (isset($_POST['submit'])) {
        $date = $_POST['date'];
        $date_time = new DateTime($date);

        // Convert to start and end date for the last 24 hours
        $start_date_24h = $date_time->format('Y-m-d 00:00:00');
        $end_date_24h = $date_time->modify('+1 day')->format('Y-m-d 00:00:00');

        // SQL queries for doctor and caregiver registration
        $sql_doctors_24h = "SELECT doctor_name, doctor_number FROM doctor_recruitment WHERE doctor_type='Doctor' AND doctor_name NOT LIKE 'Inditech%' AND created_at BETWEEN '$start_date_24h' AND '$end_date_24h'";
        $sql_caregivers_24h = "SELECT doctor_name, doctor_number FROM doctor_recruitment WHERE doctor_type='emo' AND doctor_name NOT LIKE 'Inditech%' AND created_at BETWEEN '$start_date_24h' AND '$end_date_24h'";
        $sql_doctors_cumulative = "SELECT doctor_name, doctor_number FROM doctor_recruitment WHERE doctor_type='Doctor' AND doctor_name NOT LIKE 'Inditech%' AND created_at <= '$end_date_24h'";
        $sql_caregivers_cumulative = "SELECT doctor_name, doctor_number FROM doctor_recruitment WHERE doctor_type='emo' AND doctor_name NOT LIKE 'Inditech%' AND created_at <= '$end_date_24h'";

        // Execute queries on the doctor_recruitment database
        $result_doctors_24h = $conn->query($sql_doctors_24h);
        $result_caregivers_24h = $conn->query($sql_caregivers_24h);
        $result_doctors_cumulative = $conn->query($sql_doctors_cumulative);
        $result_caregivers_cumulative = $conn->query($sql_caregivers_cumulative);

        // Fetch results
        $doctors_24h = $result_doctors_24h->num_rows;
        $caregivers_24h = $result_caregivers_24h->num_rows;
        $doctors_cumulative = $result_doctors_cumulative->num_rows;
        $caregivers_cumulative = $result_caregivers_cumulative->num_rows;

        // Initialize counters and arrays for free forms
        $free_form_doctors_today = 0;
        $free_form_caregivers_today = 0;
        $free_form_doctors_cumulative = 0;
        $free_form_caregivers_cumulative = 0;

        // Initialize counters for patients received forms
        $patients_received_form_24h = 0;
        $patients_received_form_cumulative = 0;

        // SQL queries for free forms sent (fetch doctor_ids from url_whatsapp table)
        $sql_free_form_doctor_ids = "SELECT DISTINCT doctor_id FROM url_whatsapp";
        $result_free_form_doctor_ids = $form_db->query($sql_free_form_doctor_ids);

        // Loop through each distinct doctor_id
        while ($row = $result_free_form_doctor_ids->fetch_assoc()) {
            $doctor_id = $row['doctor_id'];
            $doctor_id_escaped = $form_db->real_escape_string($doctor_id);

            // Check if free form was sent today
            $sql_check_today = "
                SELECT COUNT(*) AS count FROM url_whatsapp
                WHERE doctor_id = '$doctor_id_escaped' AND DATE(`created_at`) = '$date'
            ";
            $result_check_today = $form_db->query($sql_check_today);
            $count_today = $result_check_today->fetch_assoc()['count'];
            if ($count_today > 0) {
                $sql_check_type = "SELECT doctor_type, doctor_name, doctor_number FROM doctor_recruitment WHERE doctor_code = '$doctor_id_escaped'";
                $result_check_type = $conn->query($sql_check_type);
                if ($result_check_type->num_rows > 0) {
                    $doctor_data = $result_check_type->fetch_assoc();
                    $doctor_type = $doctor_data['doctor_type'];
                    $doctor_name = $doctor_data['doctor_name'];
                    $doctor_number = $doctor_data['doctor_number'];
                    if (!startsWithInditech($doctor_name)) {
                        if ($doctor_type == 'Doctor') {
                            $free_form_doctors_today++;
                        } elseif ($doctor_type == 'emo') {
                            $free_form_caregivers_today++;
                        }
                    }
                }
            }

            // Check if free form was sent cumulatively up to the end date
            $sql_check_cumulative = "
                SELECT COUNT(*) AS count FROM url_whatsapp
                WHERE doctor_id = '$doctor_id_escaped' AND `created_at` <= '$end_date_24h'
            ";
            $result_check_cumulative = $form_db->query($sql_check_cumulative);
            $count_cumulative = $result_check_cumulative->fetch_assoc()['count'];
            if ($count_cumulative > 0) {
                $sql_check_type = "SELECT doctor_type, doctor_name, doctor_number FROM doctor_recruitment WHERE doctor_code = '$doctor_id_escaped'";
                $result_check_type = $conn->query($sql_check_type);
                if ($result_check_type->num_rows > 0) {
                    $doctor_data = $result_check_type->fetch_assoc();
                    $doctor_type = $doctor_data['doctor_type'];
                    $doctor_name = $doctor_data['doctor_name'];
                    $doctor_number = $doctor_data['doctor_number'];
                    if (!startsWithInditech($doctor_name)) {
                        if ($doctor_type == 'Doctor') {
                            $free_form_doctors_cumulative++;
                        } elseif ($doctor_type == 'emo') {
                            $free_form_caregivers_cumulative++;
                        }
                    }
                }
            }

            // Count patients who received the free form today
            $sql_check_patients_today = "
                SELECT COUNT(*) AS count FROM url_whatsapp
                WHERE doctor_id = '$doctor_id_escaped' AND DATE(`created_at`) = '$date'
            ";
            $result_check_patients_today = $form_db->query($sql_check_patients_today);
            $patients_received_form_24h += $result_check_patients_today->fetch_assoc()['count'];

            // Count patients who received the free form cumulatively
            $sql_check_patients_cumulative = "
                SELECT COUNT(*) AS count FROM url_whatsapp
                WHERE doctor_id = '$doctor_id_escaped' AND `created_at` <= '$end_date_24h'
            ";
            $result_check_patients_cumulative = $form_db->query($sql_check_patients_cumulative);
            $patients_received_form_cumulative += $result_check_patients_cumulative->fetch_assoc()['count'];
        }

        // Initialize counters and arrays for paid product orders
        $paid_product_doctors_24h = 0;
        $paid_product_caregivers_24h = 0;
        $paid_product_doctors_cumulative = 0;
        $paid_product_caregivers_cumulative = 0;

        // Fetch unique doctor numbers from dynamic_discount table
        $sql_paid_product_doctor_ids = "SELECT DISTINCT doctor_number FROM dynamic_discount";
        $result_paid_product_doctor_ids = $conn->query($sql_paid_product_doctor_ids);

        // Loop through each distinct doctor_number
        while ($row = $result_paid_product_doctor_ids->fetch_assoc()) {
            $doctor_number = $row['doctor_number'];
            $doctor_number_escaped = $conn->real_escape_string($doctor_number);

            // Check if paid product was ordered in the last 24 hours
            $sql_check_paid_24h = "
                SELECT COUNT(*) AS count FROM dynamic_discount
                WHERE doctor_number = '$doctor_number_escaped' AND `created_at` BETWEEN '$start_date_24h' AND '$end_date_24h'
            ";
            $result_check_paid_24h = $conn->query($sql_check_paid_24h);
            $count_paid_24h = $result_check_paid_24h->fetch_assoc()['count'];
            if ($count_paid_24h > 0) {
                $sql_check_type = "SELECT doctor_type, doctor_name, doctor_number FROM doctor_recruitment WHERE doctor_number = '$doctor_number_escaped'";
                $result_check_type = $conn->query($sql_check_type);
                if ($result_check_type->num_rows > 0) {
                    $doctor_data = $result_check_type->fetch_assoc();
                    $doctor_type = $doctor_data['doctor_type'];
                    $doctor_name = $doctor_data['doctor_name'];
                    $doctor_number = $doctor_data['doctor_number'];
                    if (!startsWithInditech($doctor_name)) {
                        if ($doctor_type == 'Doctor') {
                            $paid_product_doctors_24h++;
                        } elseif ($doctor_type == 'emo') {
                            $paid_product_caregivers_24h++;
                        }
                    }
                }
            }

            // Check if paid product was ordered cumulatively up to the end date
            $sql_check_paid_cumulative = "
                SELECT COUNT(*) AS count FROM dynamic_discount
                WHERE doctor_number = '$doctor_number_escaped' AND `created_at` <= '$end_date_24h'
            ";
            $result_check_paid_cumulative = $conn->query($sql_check_paid_cumulative);
            $count_paid_cumulative = $result_check_paid_cumulative->fetch_assoc()['count'];
            if ($count_paid_cumulative > 0) {
                $sql_check_type = "SELECT doctor_type, doctor_name, doctor_number FROM doctor_recruitment WHERE doctor_number = '$doctor_number_escaped'";
                $result_check_type = $conn->query($sql_check_type);
                if ($result_check_type->num_rows > 0) {
                    $doctor_data = $result_check_type->fetch_assoc();
                    $doctor_type = $doctor_data['doctor_type'];
                    $doctor_name = $doctor_data['doctor_name'];
                    $doctor_number = $doctor_data['doctor_number'];
                    if (!startsWithInditech($doctor_name)) {
                        if ($doctor_type == 'Doctor') {
                            $paid_product_doctors_cumulative++;
                        } elseif ($doctor_type == 'emo') {
                            $paid_product_caregivers_cumulative++;
                        }
                    }
                }
            }
        }

        // New SQL queries for product counts
        $sql_test_products_24h = "
            SELECT COUNT(*) AS count FROM form_submissions
            WHERE product_name LIKE 'Test%' AND created_at BETWEEN '$start_date_24h' AND '$end_date_24h'
        ";
        $sql_emoscreen_products_24h = "
            SELECT COUNT(*) AS count FROM form_submissions
            WHERE product_name LIKE 'EmoScreen%' AND created_at BETWEEN '$start_date_24h' AND '$end_date_24h'
        ";

        $sql_test_products_cumulative = "
            SELECT COUNT(*) AS count FROM form_submissions
            WHERE product_name LIKE 'Test%' AND created_at <= '$end_date_24h'
        ";
        $sql_emoscreen_products_cumulative = "
            SELECT COUNT(*) AS count FROM form_submissions
            WHERE product_name LIKE 'EmoScreen%' AND created_at <= '$end_date_24h'
        ";

        // Execute product queries
        $result_test_products_24h = $form_db->query($sql_test_products_24h);
        $result_emoscreen_products_24h = $form_db->query($sql_emoscreen_products_24h);
        $result_test_products_cumulative = $form_db->query($sql_test_products_cumulative);
        $result_emoscreen_products_cumulative = $form_db->query($sql_emoscreen_products_cumulative);

        // Fetch product counts
        $test_products_24h = $result_test_products_24h->fetch_assoc()['count'];
        $emoscreen_products_24h = $result_emoscreen_products_24h->fetch_assoc()['count'];
        $test_products_cumulative = $result_test_products_cumulative->fetch_assoc()['count'];
        $emoscreen_products_cumulative = $result_emoscreen_products_cumulative->fetch_assoc()['count'];

        // Display results
        echo "<h2>Results for " . htmlspecialchars($date) . "</h2>";
        echo "<table class='report-table'>";
        echo "<tr class='report-header'><th></th><th>Last 24 hours</th><th>Cumulative</th></tr>";
        echo "<tr><td>Number of doctors registered</td><td><a href='doctor_names.php?type=doctors&timeframe=24h&date=" . urlencode($date) . "'>" . htmlspecialchars($doctors_24h) . "</a></td><td><a href='doctor_names.php?type=doctors&timeframe=cumulative&date=" . urlencode($date) . "'>" . htmlspecialchars($doctors_cumulative) . "</a></td></tr>";
        echo "<tr><td>Number of caregivers registered</td><td><a href='doctor_names.php?type=caregivers&timeframe=24h&date=" . urlencode($date) . "'>" . htmlspecialchars($caregivers_24h) . "</a></td><td><a href='doctor_names.php?type=caregivers&timeframe=cumulative&date=" . urlencode($date) . "'>" . htmlspecialchars($caregivers_cumulative) . "</a></td></tr>";
        echo "<tr><td>Number of doctors who have ordered the paid product</td><td><a href='doctor_names.php?type=paid_doctors&timeframe=24h&date=" . urlencode($date) . "'>" . htmlspecialchars($paid_product_doctors_24h) . "</a></td><td><a href='doctor_names.php?type=paid_doctors&timeframe=cumulative&date=" . urlencode($date) . "'>" . htmlspecialchars($paid_product_doctors_cumulative) . "</a></td></tr>";
        echo "<tr><td>Number of caregivers who have ordered the paid product</td><td><a href='doctor_names.php?type=paid_caregivers&timeframe=24h&date=" . urlencode($date) . "'>" . htmlspecialchars($paid_product_caregivers_24h) . "</a></td><td><a href='doctor_names.php?type=paid_caregivers&timeframe=cumulative&date=" . urlencode($date) . "'>" . htmlspecialchars($paid_product_caregivers_cumulative) . "</a></td></tr>";
        echo "<tr><td>Number of doctors who have sent the free form to patients</td><td><a href='doctor_names.php?type=free_doctors&timeframe=24h&date=" . urlencode($date) . "'>" . htmlspecialchars($free_form_doctors_today) . "</a></td><td><a href='doctor_names.php?type=free_doctors&timeframe=cumulative&date=" . urlencode($date) . "'>" . htmlspecialchars($free_form_doctors_cumulative) . "</a></td></tr>";
        echo "<tr><td>Number of caregivers who have sent the free form to patients</td><td><a href='doctor_names.php?type=free_caregivers&timeframe=24h&date=" . urlencode($date) . "'>" . htmlspecialchars($free_form_caregivers_today) . "</a></td><td><a href='doctor_names.php?type=free_caregivers&timeframe=cumulative&date=" . urlencode($date) . "'>" . htmlspecialchars($free_form_caregivers_cumulative) . "</a></td></tr>";
        echo "<tr><td>Number of patients who have received the free form</td><td>" . htmlspecialchars($patients_received_form_24h) . "</td><td>" . htmlspecialchars($patients_received_form_cumulative) . "</td></tr>";
        echo "<tr><td>Total number of paid products received on the system</td><td>" . htmlspecialchars($paid_product_doctors_24h + $paid_product_caregivers_24h) . "</td><td>" . htmlspecialchars($paid_product_doctors_cumulative + $paid_product_caregivers_cumulative) . "</td></tr>";
        echo "</table>";
    }
    ?>
</body>
</html>
