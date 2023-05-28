<submission-management>

    <!--  Search -->
    <div class="ui icon input">
        <input type="text" placeholder="Search..." ref="search" onkeyup="{ filter.bind(this, undefined) }">
        <i class="search icon"></i>
    </div>
    <button class="ui red right floated labeled icon button {disabled: marked_submissions.length === 0}" onclick="{delete_submissions}">
        <i class="icon delete"></i>
        Delete Selected Submissions
    </button>

    <!-- Data Table -->
    <table class="ui {selectable: submissions.length > 0} celled compact table">
        <thead>
        <tr>
            <th>File Name</th>
            <th>Competition in</th>
            <th width="175px">Size</th>
            <th width="125px">Uploaded</th>
            <th width="60px">Public</th>
            <th width="50px">Delete?</th>
            <th width="25px"></th>
        </tr>
        </thead>
        <tbody>
        <tr each="{ submission, index in submissions }"
            class="submission-row"
            onclick="{show_info_modal.bind(this, submission)}">
            <!--  show file name if exists otherwise show name(for old submissions)  -->
            <td>{ submission.file_name || submission.name }</td>
            <!--  show compeition name as link if competition is available -->
            <td if="{submission.competition}"><a class="link-no-deco" target="_blank" href="../competitions/{ submission.competition.id }">{ submission.competition.title }</a></td>
            <!--  show empty td if competition is not available  -->
            <td if="{!submission.competition}"></td>
            <td>{ format_file_size(submission.file_size) }</td>
            <td>{ timeSince(Date.parse(submission.created_when)) } ago</td>
            <td class="center aligned">
                <i class="checkmark box icon green" show="{ submission.is_public }"></i>
            </td>
            <td class="center aligned">
                <button class="ui mini button red icon" onclick="{ delete_submission.bind(this, submission) }">
                    <i class="icon delete"></i>
                </button>
            </td>
            <td class="center aligned">
                <div class="ui fitted checkbox">
                    <input type="checkbox" name="delete_checkbox" onclick="{ mark_submission_for_deletion.bind(this, submission) }">
                    <label></label>
                </div>
            </td>
        </tr>

        <tr if="{submissions.length === 0}">
            <td class="center aligned" colspan="6">
                <em>No Submissions Yet!</em>
            </td>
        </tr>
        </tbody>
        <tfoot>

        <!-- Pagination -->
        <tr>
            <th colspan="8" if="{submissions.length > 0}">
                <div class="ui right floated pagination menu" if="{submissions.length > 0}">
                    <a show="{!!_.get(pagination, 'previous')}" class="icon item" onclick="{previous_page}">
                        <i class="left chevron icon"></i>
                    </a>
                    <div class="item">
                        <label>{page}</label>
                    </div>
                    <a show="{!!_.get(pagination, 'next')}" class="icon item" onclick="{next_page}">
                        <i class="right chevron icon"></i>
                    </a>
                </div>
            </th>
        </tr>
        </tfoot>
    </table>

    <div ref="info_modal" class="ui modal">
        <div class="header">
            {selected_row.file_name || selected_row.name}
        </div>
        <div class="content">
            <h3>Details</h3>

            <table class="ui basic table">
                <thead>
                <tr>
                    <th>Key</th>
                    <th>Competition in</th>
                    <th>Created By</th>
                    <th>Created</th>
                    <th>Type</th>
                    <th>Public</th>
                </tr>
                </thead>
                <tbody>
                <tr>
                    <td>{selected_row.key}</td>
                    <!--  show compeition name as link if competition is available -->
                    <td if="{selected_row.competition}"><a class="link-no-deco" target="_blank" href="../competitions/{ selected_row.competition.id }">{ selected_row.competition.title }</a></td>
                    <!--  show empty td if competition is not available  -->
                    <td if="{!selected_row.competition}"></td>
                    <td>{selected_row.created_by}</td>
                    <td>{pretty_date(selected_row.created_when)}</td>
                    <td>{_.startCase(selected_row.type)}</td>
                    <td>{_.startCase(selected_row.is_public)}</td>
                </tr>
                </tbody>
            </table>
            <virtual if="{!!selected_row.description}">
                <div>Description:</div>
                <div class="ui segment">
                    {selected_row.description}
                </div>
            </virtual>
        </div>
        <div class="actions">
            <button show="{selected_row.created_by === CODALAB.state.user.username}"
                class="ui primary icon button" onclick="{toggle_is_public}">
                <i class="share icon"></i> {selected_row.is_public ? "Make Private" : "Make Public"}
            </button>
            <a href="{URLS.DATASET_DOWNLOAD(selected_row.key)}" class="ui green icon button">
                <i class="download icon"></i>Download File
            </a>
            <button class="ui cancel button">Close</button>
        </div>
    </div>

    <script>
        var self = this
        self.mixin(ProgressBarMixin)

        /*---------------------------------------------------------------------
         Init
        ---------------------------------------------------------------------*/
        self.errors = []
        self.submissions = []
        self.selected_row = {}
        self.marked_submissions = []


        self.page = 1

        self.one("mount", function () {
            $(".ui.dropdown", self.root).dropdown()
            $(".ui.checkbox", self.root).checkbox()
            self.update_submissions()
        })

        self.show_info_modal = function (row, e) {
            // Return here so the info modal doesn't pop up when a checkbox is clicked
            if (e.target.type === 'checkbox') {
                return
            }
            self.selected_row = row
            self.update()
            $(self.refs.info_modal).modal('show')
        }


        /*---------------------------------------------------------------------
         Methods
        ---------------------------------------------------------------------*/
        self.pretty_date = date => luxon.DateTime.fromISO(date).toLocaleString(luxon.DateTime.DATE_FULL)

        self.filter = function (filters) {
            let type = $(self.refs.type_filter).val()
            filters = filters || {}
            _.defaults(filters, {
                type: type === '-' ? '' : type,
                search: $(self.refs.search).val(),
                page: 1,
            })
            self.page = filters.page
            self.update_submissions(filters)
        }

        self.next_page = function () {
            if (!!self.pagination.next) {
                self.page += 1
                self.filter({page: self.page})
            } else {
                alert("No valid page to go to!")
            }
        }
        self.previous_page = function () {
            if (!!self.pagination.previous) {
                self.page -= 1
                self.filter({page: self.page})
            } else {
                alert("No valid page to go to!")
            }
        }

        self.update_submissions = function (filters) {
            filters = filters || {}
            filters.type = "submission"
            CODALAB.api.get_datasets(filters)
                .done(function (data) {
                    self.submissions = data.results
                    self.pagination = {
                        "count": data.count,
                        "next": data.next,
                        "previous": data.previous
                    }
                    self.update()
                })
                .fail(function (response) {
                    toastr.error("Could not load submissions...")
                })
        }

        self.delete_submission = function (submission, e) {
            name = submission.file_name || submission.name
            if (confirm(`Are you sure you want to delete '${name}'?`)) {
                CODALAB.api.delete_dataset(submission.id)
                    .done(function () {
                        self.update_submissions()
                        toastr.success("Submission deleted successfully!")
                    })
                    .fail(function (response) {
                        toastr.error(response.responseJSON['error'])
                    })
            }
            event.stopPropagation()
        }

        self.delete_submissions = function () {
            if (confirm(`Are you sure you want to delete multiple submissions?`)) {
                CODALAB.api.delete_datasets(self.marked_submissions)
                    .done(function () {
                        self.update_submissions()
                        toastr.success("Submission deleted successfully!")
                        self.marked_submissions = []
                    })
                    .fail(function (response) {
                        for (e in response.responseJSON) {
                            toastr.error(`${e}: '${response.responseJSON[e]}'`)
                        }
                    })
            }
            event.stopPropagation()
        }

        self.clear_form = function () {
            // Clear form
            $(':input', self.refs.form)
                .not(':button, :submit, :reset, :hidden')
                .val('')
                .removeAttr('checked')
                .removeAttr('selected');

            $('.dropdown', self.refs.form).dropdown('restore defaults')

            self.errors = {}
            self.update()
        }

        self.check_form = function (event) {
            if (event) {
                event.preventDefault()
            }

       

            // Let's do some quick validation
            self.errors = {}
            var validate_data = get_form_data(self.refs.form)

            var required_fields = ['name', 'type', 'data_file']
            required_fields.forEach(field => {
                if (validate_data[field] === '') {
                    self.errors[field] = "This field is required"
                }
            })

            if (Object.keys(self.errors).length > 0) {
                // display errors and drop out
                self.update()
                return
            }

            
        }

        self.toggle_is_public = () => {
            let message = self.selected_row.is_public
                ? 'Are you sure you want to make this submission private? It will no longer be available to other users.'
                : 'Are you sure you want to make this submission public? It will become visible to everyone'
            if (confirm(message)) {
                CODALAB.api.update_dataset(self.selected_row.id, {id: self.selected_row.id, is_public: !self.selected_row.is_public})
                    .done(data => {
                        toastr.success('Submission updated')
                        $(self.refs.info_modal).modal('hide')
                        self.filter()
                    })
                    .fail(resp => {
                        toastr.error(resp.responseJSON['is_public'])
                    })
            }
        }

        self.mark_submission_for_deletion = function(submission, e) {
            if (e.target.checked) {
                self.marked_submissions.push(submission.id)
            }
            else {
                self.marked_submissions.splice(self.marked_submissions.indexOf(submission.id), 1)
            }
        }

        // Function to format file size 
        self.format_file_size = function(file_size) {
            // parse file size from string to float
            try {
                n = parseFloat(file_size)
            }
            catch(err) {
                // return empty string if parsing fails
                return ""
            }
            // constant units to show with files size
            // file size is in KB, converting it to MB and GB 
            const units = ['KB', 'MB', 'GB']
            // loop incrementer for selecting desired unit
            let i = 0
            // loop over n until it is greater than 1000
            while(n >= 1000 && ++i){
                n = n/1000;
            }
            // restrict file size to 1 decimal number concatinated with unit
            return(n.toFixed(1) + ' ' + units[i]);
        }

    </script>

    <style type="text/stylus">
        .submission-row:hover
            cursor pointer
    </style>
</submission-management>
