<?php
include("config/constants.php");
$currentUrl = $_SERVER['REQUEST_URI'];
$brand_id = '';

// Use a regular expression to extract the value of 'whno'
preg_match('/\/Brands_Report_Page\/(\w+)/', $currentUrl, $matches);
$brand_id = $matches[1];

// $brand_id' = $_GET['brandId'];

?>
<!DOCTYPE html>
<html>

<head>
	<title>Brand report</title>
	<link rel="stylesheet" type="text/css" href="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/styles.css">
	<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha3/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-KK94CHFLLe+nY2dmCWGMq91rCGa5gtU4mk92HdvYe+M/SXH301p5ILy+dN9+nJOZ" crossorigin="anonymous">
	<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha3/dist/js/bootstrap.bundle.min.js" integrity="sha384-ENjdO4Dr2bkBIFxQpeoTz1HIcje39Wm4jDKdf19U8gI4ddQ3GYNS7NTKfAdVQSZe" crossorigin="anonymous"></script>
</head>

<body>
	<main>
		<h1>Brand Report</h1>
		<?php
		$sql = "SELECT `doctor_id`, `start_date`, `end_date` FROM `tracking` WHERE brand_id='$brand_id'";
		$result3 = $conn->query($sql);
		$current_date = date('Y-m-d');

		if ($result3->num_rows > 0) {
			$row3 = $result3->fetch_assoc();
			$doctor_id = $row3['doctor_id'];
			$start_date = $row3['start_date'];
			$end_date = $row3['end_date'];
		}
		?>
		<form method="POST" action="https://<?php echo $reports; ?>.<?php echo $cpd; ?>/index_copy.php/<?php echo $brand_id; ?>">
			<div class="mb-3 col-2">
				<label class="form-label">Filter by Date:</label>
				<input type="date" class="form-control" id="date" name="date" onchange="this.form.submit()">
			</div>
		</form>
		<?php
		if ($_SERVER["REQUEST_METHOD"] === "POST") {
			$date = $_POST["date"];
			echo "<p>You selected the date: " . $date . "</p>";

			$query2 = "SELECT `product_id` FROM `tracking` WHERE `start_date` <= '$date' AND `end_date` >= '$date' AND brand_id='$brand_id'";
			$result2 = $conn->query($query2);
			$row2 = $result2->fetch_assoc();
			if (isset($row2['product_id'])) {
				$product_id = $row2['product_id'];
				$db_table = dbTable($product_id);
			}
		}
		function dbTable($x)
		{
			$db_table = array(
				79 => "Self Dietary Assessment  ( Age 4 yrs or more)",
				80 => "Dietary Assessment",
				81 => "EQ Enhancement Screening Tool",
				82 => "EQ Enhancement Screening Tool - 0 to 3 years",
				83 => "EQ Enhancement Screening Tool - 12 to 17 years",
				84 => "EQ Enhancement Screening Tool - 3 to 6 years",
				85 => "EQ Enhancement Screening Tool - 7 to 11 years",
				86 => "Growth and Development Assessment Form",
				87 => "EQ Screening Form",
				88 => "Difficulty in Urination Form",
				89 => "Cold Cough Fever for 3 days Form",
				90 => "Acute cough 7 days Form",
				91 => "Measles Screening Form",
				92 => "Dr Sanjay Bhagwant Prabhu Specialist Advice",
				93 => "Dr Satish Kamtaprasad Tiwari specialist advice",
				94 => "Dr Bhavana Lakhkar specialist advice",
				95 => "Dr Paula Goel specialist advice",
				96 => "Dr Nilesh Dattu Kumbhare specialist advice",
				97 => "Long Duration Cough Form",
				98 => "Growth issues Form",
				99 => "Vomiting (Acute) Form",
				100 => "Chronic Recurrent Allergic Rhinitis (Running nose) Form",
				101 => "Convulsion Form",
				102 => "Excess Sleepiness Form",
				103 => "Pediatric Headache Form",
				104 => "Abdominal pain Form",
				105 => "Lack of appetite Form",
				106 => "Constipation Form",
				107 => "Fever less than 4 days Form",
				108 => "Fever more than 7 days Form",
				109 => "Rapid breathing Form",
				110 => "Rash on body Form",
				111 => "Diarrhoea less than 7 days Form",
				112 => "Diarrhoea more than 7 days Form",
				113 => "Prolonged Vomiting Form",
				114 => "Common Condition Form - MHA",
				115 => "Pediatric Cancer Form",
				116 => "Primary Immunodeficiency Form",
				117 => "Breastfeeding  Program Form"
			);
			if (array_key_exists($x, $db_table)) {
				return $db_table[$x];
			} else {
				return "";
			}
		}
		function get_week($columnname, $date, $brand_id, $conn)
		{
			$dateString = new DateTime($date);
			$dateString->modify('-7 days');
			$day7 = $dateString->format('Y-m-d');
			$dateString->modify('-7 days');
			$day14 = $dateString->format('Y-m-d');
			$sql_last_7_days = "SELECT COUNT(DISTINCT $columnname) as interactions_count FROM tracking WHERE brand_id = '$brand_id' AND start_date >= '$day7' AND start_date <= '$date'";
			$result_last_7_days = $conn->query($sql_last_7_days);
			$sql_last_14_days = "SELECT COUNT(DISTINCT $columnname) as interactions_count FROM tracking WHERE brand_id = '$brand_id' AND start_date >= '$day14' AND start_date <= '$day7'";
			$result_last_14_days = $conn->query($sql_last_14_days);

			if ($result_last_7_days->num_rows > 0) {
				$row_last_7_days = $result_last_7_days->fetch_assoc();
				$count_last_7_days = $row_last_7_days['interactions_count'];
			} else {
				$count_last_7_days = 0;
			}

			if ($result_last_14_days->num_rows > 0) {
				$row_last_14_days = $result_last_14_days->fetch_assoc();
				$count_last_14_days = $row_last_14_days['interactions_count'];
			} else {
				$count_last_14_days = 0;
			}
			//echo $count_last_14_days;
			if ($count_last_14_days != 0) {
				$result = ($count_last_7_days - $count_last_14_days) / $count_last_14_days * 100;
			} else {
				$result = 0;
			}
			return $result;
		}
		function get_week_each($user_id, $columnname, $condcolumn, $date, $brand_id, $conn)
		{
			$dateString = new DateTime($date);
			$dateString->modify('-7 days');
			$day7 = $dateString->format('Y-m-d');
			$dateString->modify('-7 days');
			$day14 = $dateString->format('Y-m-d');
			// echo $date.$day7.$day14;
			$sql_last_7_days = "SELECT COUNT(DISTINCT field_rep_number) as interactions_count FROM `tracking` WHERE `brand_id` = '$brand_id' AND $condcolumn = '$user_id' AND start_date >= '$day7' AND start_date <= '$date'";
			$result_last_7_days = $conn->query($sql_last_7_days);
			$sql_last_14_days = "SELECT COUNT(DISTINCT field_rep_number) as interactions_count FROM `tracking` WHERE `brand_id` = '$brand_id' AND $condcolumn = '$user_id' AND start_date >= '$day14' AND start_date <= '$day7'";
			$result_last_14_days = $conn->query($sql_last_14_days);
			if ($result_last_7_days->num_rows > 0) {
				$row_last_7_days = $result_last_7_days->fetch_assoc();
				$count_last_7_days = $row_last_7_days['interactions_count'];
			} else {
				$count_last_7_days = 0;
			}

			if ($result_last_14_days->num_rows > 0) {
				$row_last_14_days = $result_last_14_days->fetch_assoc();
				$count_last_14_days = $row_last_14_days['interactions_count'];
			} else {
				$count_last_14_days = 0;
			}
			//echo $count_last_14_days;
			if ($count_last_14_days != 0) {
				$result = ($count_last_7_days - $count_last_14_days) / $count_last_14_days * 100;
			} else {
				$result = 0;
			}
			return $result;
		}
		function get_count($user_id, $columnname, $condcolumn, $brand_id, $date, $conn)
		{
			$sql_last_7_days = "SELECT COUNT(DISTINCT $columnname) as interactions_count FROM tracking WHERE brand_id = '$brand_id' AND $condcolumn = '$user_id' AND start_date = '$date'";
			$result_last_7_days = $conn->query($sql_last_7_days);

			$sql_cumulative = "SELECT COUNT(DISTINCT $columnname) as interactions_count FROM tracking WHERE brand_id = '$brand_id' AND $condcolumn = '$user_id'";
			$result_cumulative = $conn->query($sql_cumulative);

			if ($result_last_7_days->num_rows > 0) {
				$row_last_7_days = $result_last_7_days->fetch_assoc();
				$count_last_7_days = $row_last_7_days['interactions_count'];
			} else {
				$count_last_7_days = 0;
			}

			if ($result_cumulative->num_rows > 0) {
				$row_cumulative = $result_cumulative->fetch_assoc();
				$count_cumulative = $row_cumulative['interactions_count'];
			} else {
				$count_cumulative = 0;
			}
			$arr = [$count_last_7_days, $count_cumulative];
			return $arr;
		}
		function get_count_double($user_id, $columnname, $condcolumn, $user_id2, $condcolumn2, $conn, $brand_id, $date)
		{
			$sql_last_7_days = "SELECT COUNT(*) as interactions_count FROM tracking WHERE brand_id = '$brand_id' AND $condcolumn = '$user_id' AND  $condcolumn2 = '$user_id2' AND start_date = '$date'";
			$result_last_7_days = $conn->query($sql_last_7_days);

			$sql_cumulative = "SELECT COUNT(*) as interactions_count FROM tracking WHERE brand_id = '$brand_id' AND $condcolumn = '$user_id' AND  $condcolumn2 = '$user_id2'";
			$result_cumulative = $conn->query($sql_cumulative);

			if ($result_last_7_days->num_rows > 0) {
				$row_last_7_days = $result_last_7_days->fetch_assoc();
				$count_last_7_days = $row_last_7_days['interactions_count'];
			} else {
				$count_last_7_days = 0;
			}

			if ($result_cumulative->num_rows > 0) {
				$row_cumulative = $result_cumulative->fetch_assoc();
				$count_cumulative = $row_cumulative['interactions_count'];
			} else {
				$count_cumulative = 0;
			}
			$arr = [$count_last_7_days, $count_cumulative];
			return $arr;
		}

		$query = "SELECT DISTINCT field_rep_number FROM tracking WHERE brand_id='$brand_id' AND field_rep_number IS NOT NULL";
		$result = $conn->query($query);

		if ($result) {
			$rep_ids = array();
			while ($row = $result->fetch_assoc()) {
				$rep_ids[] = $row["field_rep_number"];
			}
			$result->close();
		}

		?>
		<table>
			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") {
				?>
					<th></th>
					<th>Data on date selected</th>
					<th>Cumulative data</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				if ($_SERVER["REQUEST_METHOD"] !== "POST") {
				?>
					<th></th>
					<th>Last 24 hours</th>
					<th>Cumulative</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				?>
			</tr>
			<td><b>FIELD REP ACTIVITY</b></td>
			<tr>
				<td>List of all field reps and count of doctors activated by each rep?</td>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
					<td>
						<?php
						$query11 = "SELECT COUNT(DISTINCT field_rep_number) AS num FROM tracking WHERE brand_id = '$brand_id' AND start_date='$date'";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$query11 = "SELECT COUNT(DISTINCT field_rep_number) AS num FROM tracking WHERE brand_id = '$brand_id'";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$columnname = 'field_rep_number';
						$percentage = get_week($columnname, $date, $brand_id, $conn);
						echo $percentage . '%';
						?>
					</td>
				<?php
				}
				if ($_SERVER["REQUEST_METHOD"] !== "POST") { ?>
					<td>
						<?php
						$query11 = "SELECT COUNT(DISTINCT field_rep_number) AS num FROM tracking WHERE brand_id ='$brand_id' AND date>= DATE_SUB(NOW(), INTERVAL 1 DAY)";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$query11 = "SELECT COUNT(DISTINCT field_rep_number) AS num FROM tracking WHERE brand_id = '$brand_id'";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$columnname = 'field_rep_number';
						$percentage = get_week($columnname, $current_date, $brand_id, $conn);
						echo $percentage . '%';
						?>
					</td>
				<?php
				}
				?>
			</tr>
			<td><b>DOCTOR ENGAGEMENT</b></td>
			<tr>
				<td>Total number of doctors registered</td>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
					<td>
						<?php
						$query11 = "SELECT COUNT(DISTINCT doctor_id) AS num FROM tracking WHERE brand_id = '$brand_id' AND start_date='$date'";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$query11 = "SELECT COUNT(DISTINCT doctor_id) AS num FROM tracking WHERE brand_id = '$brand_id'";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$columnname = 'doctor_id';
						$percentage = get_week($columnname, $date, $brand_id, $conn);
						echo $percentage . '%';
						?>
					</td>
				<?php
				}
				if ($_SERVER["REQUEST_METHOD"] !== "POST") { ?>
					<td>
						<?php
						$query11 = "SELECT COUNT(DISTINCT doctor_id) AS num FROM tracking WHERE brand_id ='$brand_id' AND date>= DATE_SUB(NOW(), INTERVAL 1 DAY)";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$query11 = "SELECT COUNT(DISTINCT doctor_id) AS num FROM tracking WHERE brand_id = '$brand_id'";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$columnname = 'doctor_id';
						$percentage = get_week($columnname, $current_date, $brand_id, $conn);
						echo $percentage . '%';
						?>
					</td>
				<?php
				}
				?>
			</tr>

			<tr>
				<td>Form shared with patients by doctor, reported by field rep</td>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
					<td>
						<?php
						$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '1' AND start_date='$date'";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '1' ";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
					<?php
					$columnname = '*';
					$percentage = get_week_each('1', $columnname, 'status', $date, $brand_id, $conn);
					echo $percentage . '%';
				} ?>
					</td>

					<?php
					if ($_SERVER["REQUEST_METHOD"] !== "POST") { ?>
						<td>
							<?php
							$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '1' AND date>= DATE_SUB(NOW(), INTERVAL 1 DAY)";
							$result11 = $conn->query($query11);
							$row11 = $result11->fetch_assoc();
							$num = $row11['num'];
							echo $num;
							?>
						</td>
						<td>
							<?php
							$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '1'";
							$result11 = $conn->query($query11);
							$row11 = $result11->fetch_assoc();
							$num = $row11['num'];
							echo $num;
							?>
						</td>
						<td>
						<?php
						$columnname = '*';
						$percentage = get_week_each('1', $columnname, 'status', $current_date, $brand_id, $conn);
						echo $percentage . '%';
					} ?>
						</td>

			</tr>

			<td><b>PATIENT ENGAGEMENT</b></td>

			<tr>
				<td>Number of forms filled, reported by field rep</td>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
					<td>
						<?php
						$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '2' AND start_date='$date'";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '2' ";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
					<?php
					$columnname = '*';
					$percentage = get_week_each('2', $columnname, 'status', $date, $brand_id, $conn);
					echo $percentage . '%';
				} ?>
					</td>

					<?php
					if ($_SERVER["REQUEST_METHOD"] !== "POST") { ?>
						<td>
							<?php
							$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '2' AND date>= DATE_SUB(NOW(), INTERVAL 1 DAY)";
							$result11 = $conn->query($query11);
							$row11 = $result11->fetch_assoc();
							$num = $row11['num'];
							echo $num;
							?>
						</td>
						<td>
							<?php
							$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '2'";
							$result11 = $conn->query($query11);
							$row11 = $result11->fetch_assoc();
							$num = $row11['num'];
							echo $num;
							?>
						</td>
						<td>
						<?php
						$columnname = '*';
						$percentage = get_week_each('2', $columnname, 'status', $current_date, $brand_id, $conn);
						echo $percentage . '%';
					} ?>
						</td>

			</tr>

			<!-- <tr>
				<td>Number of patient education videos viewed by patients, reported by field rep</td>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
					<td>
						<?php
						$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '4' AND start_date='$date'";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '4' ";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
					<?php
					$columnname = '*';
					$percentage = get_week_each('4', $columnname, 'status', $date, $brand_id, $conn);
					echo $percentage . '%';
				} ?>
					</td>

					<?php
					if ($_SERVER["REQUEST_METHOD"] !== "POST") { ?>
						<td>
							<?php
							$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '4' AND date>= DATE_SUB(NOW(), INTERVAL 1 DAY)";
							$result11 = $conn->query($query11);
							$row11 = $result11->fetch_assoc();
							$num = $row11['num'];
							echo $num;
							?>
						</td>
						<td>
							<?php
							$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '4'";
							$result11 = $conn->query($query11);
							$row11 = $result11->fetch_assoc();
							$num = $row11['num'];
							echo $num;
							?>
						</td>
						<td>
						<?php
						$columnname = '*';
						$percentage = get_week_each('4', $columnname, 'status', $current_date, $brand_id, $conn);
						echo $percentage . '%';
					} ?>
						</td>

			</tr> -->

			<!-- <tr>
				<td>Appointment calls initiated via system by patients, reported by field rep</td>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
					<td>
						<?php
						$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '100' AND start_date='$date'";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
						<?php
						$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '100' ";
						$result11 = $conn->query($query11);
						$row11 = $result11->fetch_assoc();
						$num = $row11['num'];
						echo $num;
						?>
					</td>
					<td>
					<?php
					$columnname = '*';
					$percentage = get_week_each('100', $columnname, 'status', $date, $brand_id, $conn);
					echo $percentage . '%';
				} ?>
					</td>

					<?php
					if ($_SERVER["REQUEST_METHOD"] !== "POST") { ?>
						<td>
							<?php
							$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '100' AND date>= DATE_SUB(NOW(), INTERVAL 1 DAY)";
							$result11 = $conn->query($query11);
							$row11 = $result11->fetch_assoc();
							$num = $row11['num'];
							echo $num;
							?>
						</td>
						<td>
							<?php
							$query11 = "SELECT COUNT(*) AS num FROM tracking WHERE brand_id = '$brand_id' AND status = '100'";
							$result11 = $conn->query($query11);
							$row11 = $result11->fetch_assoc();
							$num = $row11['num'];
							echo $num;
							?>
						</td>
						<td>
						<?php
						$columnname = '*';

						$percentage = get_week_each('100', $columnname, 'status', $current_date, $brand_id, $conn);
						echo $percentage . '%';
					} ?>
						</td>
			</tr> -->

			<tr>
				<td style='line-height:10px;' colspan=4>&nbsp;</td>
			</tr>
		</table>
		<br><br>
		<table>
			<tr>
				<h3>List of all field reps and count of doctors activated by each rep?</h3>
			</tr>
			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") {
				?>
					<th>Field rep ID:</th>
					<th>Data on date selected</th>
					<th>Cumulative data</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				if ($_SERVER["REQUEST_METHOD"] !== "POST") {
				?>
					<th>Field rep ID:</th>
					<th>Last 24 hours</th>
					<th>Cumulative</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				?>
			</tr>

			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
					<?php
					$cname = "doctor_id";
					$cond = "field_rep_number";
					foreach ($rep_ids as $user_id) {

						$value = get_count($user_id, $cname, $cond, $brand_id, $date, $conn);
						$trend = get_week_each($user_id, $cname, $cond, $date, $brand_id, $conn);
						echo "<tr><td>$user_id</td><td>$value[0]</td><td>$value[1]</td><td>$trend</td></tr>";
					}
					?>
				<?php
				}
				if ($_SERVER["REQUEST_METHOD"] !== "POST") {
					$cname = "doctor_id";
					$cond = "field_rep_number";

					$date = date('Y-m-d');
					foreach ($rep_ids as $user_id) {

						$value = get_count($user_id, $cname, $cond, $brand_id, $date, $conn);
						$trend = get_week_each($user_id, $cname, $cond, $date, $brand_id, $conn);
						echo "<tr><td>$user_id</td><td>$value[0]</td><td>$value[1]</td><td>$trend</td></tr>";
					}
				}
				?>
			</tr>

			<tr>
				<td style='line-height:10px;' colspan=4>&nbsp;</td>
			</tr>
		</table>
		<br><br>
		<table>
			<tr>
				<h3>Number of forms shared with patients, reported by field rep</h3>
			</tr>
			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") {
				?>
					<th>Field rep ID:</th>
					<th>Data on date selected</th>
					<th>Cumulative data</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				if ($_SERVER["REQUEST_METHOD"] !== "POST") {
				?>
					<th>Field rep ID:</th>
					<th>Last 24 hours</th>
					<th>Cumulative</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				?>
			</tr>
			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
				<?php
					$cname = "*";
					$cond = "field_rep_number";
					foreach ($rep_ids as $user_id) {

						$value = get_count_double($user_id, $cname, $cond, '1', 'status', $conn, $brand_id, $date);
						$trend = get_week_each($user_id, $cname, $cond, $date, $brand_id, $conn);
						echo "<tr><td>$user_id</td><td>$value[0]</td><td>$value[1]</td><td>$trend</td></tr>";
					}
				}
				?>
				<?php
				if ($_SERVER["REQUEST_METHOD"] !== "POST") { ?>
				<?php
					$cname = "*";
					$cond = "field_rep_number";
					foreach ($rep_ids as $user_id) {

						$value = get_count_double($user_id, $cname, $cond, '1', 'status', $conn, $brand_id, $date);
						$trend = get_week_each($user_id, $cname, $cond, $date, $brand_id, $conn);
						echo "<tr><td>$user_id</td><td>$value[0]</td><td>$value[1]</td><td>$trend</td></tr>";
					}
				}

				?>
			</tr>
			<tr>
				<td style='line-height:10px;' colspan=4>&nbsp;</td>
			</tr>
		</table>
		<br><br>
		<table>
			<tr>
				<h3>Number of forms filled by patients, reported by field rep</h3>
			</tr>
			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") {
				?>
					<th>Field rep ID:</th>
					<th>Data on date selected</th>
					<th>Cumulative data</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				if ($_SERVER["REQUEST_METHOD"] !== "POST") {
				?>
					<th>Field rep ID:</th>
					<th>Last 24 hours</th>
					<th>Cumulative</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				?>
			</tr>
			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
				<?php
					$cname = "*";
					$cond = "field_rep_number";
					foreach ($rep_ids as $user_id) {

						$value = get_count_double($user_id, $cname, $cond, '2', 'status', $conn, $brand_id, $date);
						$trend = get_week_each($user_id, $cname, $cond, $date, $brand_id, $conn);
						echo "<tr><td>$user_id</td><td>$value[0]</td><td>$value[1]</td><td>$trend</td></tr>";
					}
				}
				?>
				<?php
				if ($_SERVER["REQUEST_METHOD"] !== "POST") { ?>
				<?php
					$cname = "*";
					$cond = "field_rep_number";
					foreach ($rep_ids as $user_id) {

						$value = get_count_double($user_id, $cname, $cond, '2', 'status', $conn, $brand_id, $date);
						$trend = get_week_each($user_id, $cname, $cond, $date, $brand_id, $conn);
						echo "<tr><td>$user_id</td><td>$value[0]</td><td>$value[1]</td><td>$trend</td></tr>";
					}
				}

				?>
			</tr>
			<tr>
				<td style='line-height:10px;' colspan=4>&nbsp;</td>
			</tr>
		</table>
		<br><br>

		<!-- <table>
			<tr>
				<h3>Number of patient education videos viewed by patients, reported by field rep</h3>
			</tr>
			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") {
				?>
					<th>Field rep ID:</th>
					<th>Data on date selected</th>
					<th>Cumulative data</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				if ($_SERVER["REQUEST_METHOD"] !== "POST") {
				?>
					<th>Field rep ID:</th>
					<th>Last 24 hours</th>
					<th>Cumulative</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				?>
			</tr>
			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
				<?php
					$cname = "*";
					$cond = "field_rep_number";
					foreach ($rep_ids as $user_id) {

						$value = get_count_double($user_id, $cname, $cond, '4', 'status', $conn, $brand_id, $date);
						$trend = get_week_each($user_id, $cname, $cond, $date, $brand_id, $conn);
						echo "<tr><td>$user_id</td><td>$value[0]</td><td>$value[1]</td><td>$trend</td></tr>";
					}
				}
				?>
				<?php
				if ($_SERVER["REQUEST_METHOD"] !== "POST") {
					$cname = "*";
					$cond = "field_rep_number";
					foreach ($rep_ids as $user_id) {

						$value = get_count_double($user_id, $cname, $cond, '4', 'status', $conn, $brand_id, $date);
						$trend = get_week_each($user_id, $cname, $cond, $date, $brand_id, $conn);
						echo "<tr><td>$user_id</td><td>$value[0]</td><td>$value[1]</td><td>$trend</td></tr>";
					}
				}
				?>
			</tr>
			<tr>
				<td style='line-height:10px;' colspan=4>&nbsp;</td>
			</tr>
		</table>
		<br><br>
		<table>
			<tr>
				<h3>Number of clinic appointment calls initiated via system by patient, reported by field rep</h3>
			</tr>
			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") {
				?>
					<th>Field rep ID:</th>
					<th>Data on date selected</th>
					<th>Cumulative data</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				if ($_SERVER["REQUEST_METHOD"] !== "POST") {
				?>
					<th>Field rep ID:</th>
					<th>Last 24 hours</th>
					<th>Cumulative</th>
					<th>Week-on-Week Trend</th>
				<?php
				}
				?>
			</tr>
			<tr>
				<?php
				if ($_SERVER["REQUEST_METHOD"] === "POST") { ?>
				<?php
					$cname = "*";
					$cond = "field_rep_number";
					foreach ($rep_ids as $user_id) {
						$value = get_count_double($user_id, $cname, $cond, '100', 'status', $conn, $brand_id, $date);
						$trend = get_week_each($user_id, $cname, $cond, $date, $brand_id, $conn);
						echo "<tr><td>$user_id</td><td>$value[0]</td><td>$value[1]</td><td>$trend</td></tr>";
					}
				}
				?>
				<?php
				if ($_SERVER["REQUEST_METHOD"] !== "POST") { ?>
				<?php
					$cname = "*";
					$cond = "field_rep_number";
					foreach ($rep_ids as $user_id) {

						$value = get_count_double($user_id, $cname, $cond, '100', 'status', $conn, $brand_id, $date);
						$trend = get_week_each($user_id, $cname, $cond, $date, $brand_id, $conn);
						echo "<tr><td>$user_id</td><td>$value[0]</td><td>$value[1]</td><td>$trend</td></tr>";
					}
				}

				?>
			</tr>
			<tr>
				<td style='line-height:10px;' colspan='4'>&nbsp;</td>
			</tr>
		</table> -->
	</main>
</body>

</html>