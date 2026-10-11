
	$(document).ready(function() {

		function centerModal() {
			$(this).css('display', 'block');
			var $dialog = $(this).find(".modal-dialog");
			var offset = ($(window).height() - $dialog.height()) / 2;
			// Center modal vertically in window
			$dialog.css("margin-top", offset);
		}

		$('.modal').on('show.bs.modal', centerModal);

		$(window).on("resize", function() {
			$('.modal:visible').each(centerModal);
		});

		$('.orderbutton').click(function() {
			plan_overlay($(this).data('group'), $(this).data('plan'));
		});

		function plan_overlay(group, plan) {

			var html = "";
			var title = "";

			var plans =
// ------------------------------------------ BEGINING: PLANS
{
    "slabs": {
        "all": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?gid=42",
                "disabled": "false"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?gid=45",
                "disabled": "false"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?gid=46",
                "disabled": "false"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?gid=49",
                "disabled": "false"
            }
        ]
    },
    "slice": {
        "512": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1439",
                "disabled": "true"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1440",
                "disabled": "true"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1441",
                "disabled": "true"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1500",
                "disabled": "true"
            }
        ],
        "1024": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1411",
                "disabled": "true"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1413",
                "disabled": "true"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1423",
                "disabled": "true"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1501",
                "disabled": "true"
            }
        ],
        "2048": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1402",
                "disabled": "true"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1414",
                "disabled": "false"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1424",
                "disabled": "true"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1502",
                "disabled": "false"
            }
        ],
        "4096": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1403",
                "disabled": "true"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1415",
                "disabled": "false"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1425",
                "disabled": "true"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1503",
                "disabled": "true"
            }
        ],
        "8192": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1404",
                "disabled": "true"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1416",
                "disabled": "false"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1426",
                "disabled": "true"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1504",
                "disabled": "true"
            }
        ],
        "12288": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1405",
                "disabled": "true"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1417",
                "disabled": "false"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1427",
                "disabled": "true"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1505",
                "disabled": "true"
            }
        ],
        "16384": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1406",
                "disabled": "true"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1418",
                "disabled": "false"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1428",
                "disabled": "false"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1506",
                "disabled": "false"
            }
        ],
        "20480": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1407",
                "disabled": "false"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1419",
                "disabled": "false"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1429",
                "disabled": "true"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1507",
                "disabled": "false"
            }
        ],
        "24576": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1408",
                "disabled": "true"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1420",
                "disabled": "false"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1430",
                "disabled": "false"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1508",
                "disabled": "false"
            }
        ],
        "28672": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1409",
                "disabled": "true"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1421",
                "disabled": "false"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1431",
                "disabled": "false"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1509",
                "disabled": "false"
            }
        ],
        "32768": [
            {
                "location": "Las Vegas",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1410",
                "disabled": "true"
            },
            {
                "location": "New York",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1422",
                "disabled": "false"
            },
            {
                "location": "Luxembourg",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1432",
                "disabled": "false"
            },
            {
                "location": "Miami",
                "url": "https://my.frantech.ca/cart.php?a=add&pid=1510",
                "disabled": "false"
            }
        ]
    }
}
// ------------------------------------------ END: PLANS
			;

			/* KVM plans are being discontinued in favor of the slices so lets hide the order links */

			if(plans[group]) {

				$.each(plans[group][plan], function(index, data) {
                    /* Display a message that this product is out of stock and it's available on Cloudzy. */
                    outOfStock = data['disabled'] === "true";
					html += '<a ' + (outOfStock ? 'onclick="$(\'#modal\').modal(\'hide\');$(\'#outofstock_modal\').modal(\'show\')"' : 'href="' + data['url'] + '"') + ' class="button locationbutton" style="width: 35%;">' + data['location'] + '</a>';
				});

                title = 'Please pick a location';

                $('#modal .modal-title').html(title);
                $('#modal .modal-body').html(html);
                $('#modal').modal('show');
			}

		}

	});
