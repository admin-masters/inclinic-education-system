<?php
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
include '../../config/constants.php'; 

$brand_campaign_id = isset($_GET['brand_campaign_id']) ? $_GET['brand_campaign_id'] : '';
$csv_file = 'report.csv';

// Pagination settings
$rows_per_page = 50;
$page = isset($_GET['page']) ? (int)$_GET['page'] : 1;
$offset = ($page - 1) * $rows_per_page;

$data_rows = [];
if (file_exists($csv_file) && is_readable($csv_file)) {
    if (($handle = fopen($csv_file, 'r')) !== false) {
        $header = fgetcsv($handle);
        while (($data = fgetcsv($handle)) !== false) {
            $data_rows[] = $data;
        }
        fclose($handle);
    }
}
$total_rows = count($data_rows);
$total_pages = ceil($total_rows / $rows_per_page);
$current_page_data = array_slice($data_rows, $offset, $rows_per_page);

// Fetch all transaction dates in bulk
$employee_codes = array_column($current_page_data, 1);
// Assuming doctor's number is in index 5 (as used in your key below)
$doctor_numbers = array_column($current_page_data, 5); 

$placeholders = implode(',', array_fill(0, count($employee_codes), '?'));

// Define collateral IDs (337 and 407 are mini CME; 387 is the case study)
$collateral_ids = [337, 387, 407];
$collateral_placeholders = implode(',', array_fill(0, count($collateral_ids), '?'));

$query = "SELECT collateral_id, field_id, doctor_number, transaction_date, viewed 
          FROM MHlvVeLT 
          WHERE collateral_id IN ($collateral_placeholders) 
          AND field_id IN ($placeholders) 
          AND doctor_number IN ($placeholders)";
          
$stmt = $conn->prepare($query);
$params = array_merge($collateral_ids, $employee_codes, $doctor_numbers);
$stmt->bind_param(str_repeat('s', count($params)), ...$params);
$stmt->execute();
$result = $stmt->get_result();

$transaction_dates = [];
while ($row = $result->fetch_assoc()) {
    $key = $row['collateral_id'] . '_' . $row['field_id'] . '_' . $row['doctor_number'];
    $transaction_dates[$key]['shared'] = $row['transaction_date'];
    if ($row['viewed'] == 1) {
        $transaction_dates[$key]['viewed'] = $row['transaction_date'];
    }
}
$stmt->close();
?>

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Field ID Data</title>
  <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">
  <style>
      .btn-container {
          display: flex;
          gap: 10px;
          margin-bottom: 20px;
      }
      .table-container {
          overflow-x: auto;
      }
      .pagination {
          justify-content: center;
      }
  </style>
</head>
<body>
  <div class="container mt-5">
    <div class="btn-container">
      <a href="https://<?= $reports ?>.<?= $cpd ?>/reports/collateral_report_portal/dashboard.php" class="btn btn-primary">Dashboard</a>
      <a href="download_csv1.php?brand_campaign_id=<?= urlencode($brand_campaign_id) ?>" class="btn btn-success">Download CSV</a>
    </div>
    <div class="table-container">
      <table class="table table-bordered table-striped">
        <thead class="thead-dark">
          <tr>
            <th>NAME OF STAFF</th>
            <th>EMPLOYEE CODE</th>
            <th>HQ</th>
            <th>STAFF WHATSAPP NUMBER</th>
            <th>PEDIATRICIAN'S NAME</th>
            <th>PEDIATRICIAN'S WHATSAPP NUMBER</th>
            <th>STATE</th>
            <th>DATE OF LINK OF "Case Study - The Science of Baby Skin" SHARED BY STAFF</th>
            <th>DATE OF LINK "Case Study - The Science of Baby Skin" OPENED BY DR.</th>
            <th>DATE OF LINK OF "Mini CME - The Science of Baby Skin" SHARED BY STAFF</th>
            <th>DATE OF LINK "Mini CME - The Science of Baby Skin"  OPENED BY DR.</th>
            <th>DATE OF LINK OF "Mini CME - Diaper Dermatitis SHARED BY STAFF</th>
            <th>DATE OF LINK "Mini CME -Mini CME - Diaper Dermatitis"  OPENED BY DR.</th>
          </tr>
        </thead>
        <tbody>
          <?php foreach ($current_page_data as $data): ?>
            <?php
              // Create keys for each collateral id using employee code and doctor's number (assumed at index 5)
              $case_study_key = "387_{$data[1]}_{$data[5]}";
              $mini_cme_key_407 = "407_{$data[1]}_{$data[5]}";
              $mini_cme_key_337 = "337_{$data[1]}_{$data[5]}";

              $case_study_shared = $transaction_dates[$case_study_key]['shared'] ?? 'Not Found';
              $case_study_viewed = $transaction_dates[$case_study_key]['viewed'] ?? 'Not Found';

              $mini_cme_shared_407 = $transaction_dates[$mini_cme_key_407]['shared'] ?? 'Not Found';
              $mini_cme_viewed_407 = $transaction_dates[$mini_cme_key_407]['viewed'] ?? 'Not Found';

              $mini_cme_shared_337 = $transaction_dates[$mini_cme_key_337]['shared'] ?? 'Not Found';
              $mini_cme_viewed_337 = $transaction_dates[$mini_cme_key_337]['viewed'] ?? 'Not Found';
            ?>
            <tr>
              <td><?= htmlspecialchars($data[0]) ?></td>
              <td><?= htmlspecialchars($data[1]) ?></td>
              <td><?= htmlspecialchars($data[2]) ?></td>
              <td><?= htmlspecialchars($data[3]) ?></td>
              <td><?= htmlspecialchars($data[4]) ?></td>
              <td><?= htmlspecialchars($data[5]) ?></td>
              <td><?= htmlspecialchars($data[6]) ?></td>
              <td><?= $case_study_shared ?></td>
              <td><?= $case_study_viewed ?></td>
              <td><?= $mini_cme_shared_407 ?></td>
              <td><?= $mini_cme_viewed_407 ?></td>
              <td><?= $mini_cme_shared_337 ?></td>
              <td><?= $mini_cme_viewed_337 ?></td>
            </tr>
          <?php endforeach; ?>
        </tbody>
      </table>
    </div>
    <nav>
      <ul class="pagination">
        <?php for ($i = 1; $i <= $total_pages; $i++): ?>
          <li class="page-item <?= ($i === $page) ? 'active' : '' ?>">
            <a class="page-link" href="?page=<?= $i ?>&brand_campaign_id=<?= urlencode($brand_campaign_id) ?>"><?= $i ?></a>
          </li>
        <?php endfor; ?>
      </ul>
    </nav>
  </div>
  <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
<?php $conn->close(); ?>
