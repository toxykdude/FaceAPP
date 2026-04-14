/**
 * Members list page with table, search, and filtering.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Button,
    Card,
    CardContent,
    TextField,
    Typography,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TablePagination,
    Chip,
    IconButton,
    InputAdornment,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogContentText,
    DialogActions,
} from '@mui/material';
import {
    Add as AddIcon,
    Search as SearchIcon,
    Edit as EditIcon,
    Delete as DeleteIcon,
    FaceRetouchingNatural as EnrollIcon,
    CardMembership as CardMembershipIcon,
} from '@mui/icons-material';
import { membersApi, Member } from '@/api/members';

export const MembersList: React.FC = () => {
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

    const deleteMutation = useMutation({
        mutationFn: (id: string) => membersApi.deleteMember(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['members'] });
            setDeleteTarget(null);
        },
        onError: (error: any) => {
            alert('Error deleting member: ' + (error?.response?.data?.detail || error?.message || 'Unknown error'));
            setDeleteTarget(null);
        },
    });

    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(25);
    const [search, setSearch] = useState('');

    const { data, isLoading } = useQuery({
        queryKey: ['members', page, rowsPerPage, search],
        queryFn: () =>
            membersApi.getMembers({
                skip: page * rowsPerPage,
                limit: rowsPerPage,
                search: search || undefined,
            }),
    });

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'active':
                return 'success';
            case 'inactive':
                return 'default';
            case 'suspended':
                return 'error';
            default:
                return 'default';
        }
    };

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h4">Members</Typography>
                <Button
                    variant="contained"
                    startIcon={<AddIcon />}
                    onClick={() => navigate('/members/new')}
                >
                    Add Member
                </Button>
            </Box>

            <Card>
                <CardContent>
                    <TextField
                        fullWidth
                        placeholder="Search by name, email, or ID..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        InputProps={{
                            startAdornment: (
                                <InputAdornment position="start">
                                    <SearchIcon />
                                </InputAdornment>
                            ),
                        }}
                        sx={{ mb: 2 }}
                    />

                    <TableContainer>
                        <Table>
                            <TableHead>
                                <TableRow>
                                    <TableCell>Name</TableCell>
                                    <TableCell>ID</TableCell>
                                    <TableCell>Email</TableCell>
                                    <TableCell>Phone</TableCell>
                                    <TableCell>Status</TableCell>
                                    <TableCell>Enrolled</TableCell>
                                    <TableCell align="right">Actions</TableCell>
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {isLoading ? (
                                    <TableRow>
                                        <TableCell colSpan={7} align="center">
                                            Loading...
                                        </TableCell>
                                    </TableRow>
                                ) : data?.members.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={7} align="center">
                                            No members found
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    data?.members.map((member: Member) => (
                                        <TableRow key={member.id} hover>
                                            <TableCell>
                                                {member.first_name} {member.last_name}
                                            </TableCell>
                                            <TableCell>{member.id_number || '—'}</TableCell>
                                            <TableCell>{member.email}</TableCell>
                                            <TableCell>{member.phone}</TableCell>
                                            <TableCell>
                                                <Chip
                                                    label={member.status}
                                                    color={getStatusColor(member.status)}
                                                    size="small"
                                                />
                                            </TableCell>
                                            <TableCell>
                                                <Chip
                                                    label={member.facial_data_enrolled ? 'Yes' : 'No'}
                                                    color={member.facial_data_enrolled ? 'success' : 'default'}
                                                    size="small"
                                                />
                                            </TableCell>
                                            <TableCell align="right">
                                                <IconButton
                                                    size="small"
                                                    onClick={() => navigate(`/members/${member.id}/edit`)}
                                                    title="Edit Member"
                                                    color="primary"
                                                >
                                                    <EditIcon />
                                                </IconButton>
                                                <IconButton
                                                    size="small"
                                                    onClick={() => navigate(`/members/${member.id}/membership`)}
                                                    title="Membership"
                                                    color="secondary"
                                                >
                                                    <CardMembershipIcon />
                                                </IconButton>
                                                <IconButton
                                                    size="small"
                                                    onClick={() => navigate(`/members/${member.id}/enroll`)}
                                                    title="Face Enrollment"
                                                    color={member.facial_data_enrolled ? 'success' : 'warning'}
                                                >
                                                    <EnrollIcon />
                                                </IconButton>
                                                <IconButton size="small" title="Delete" color="error" onClick={() => setDeleteTarget(member.id)}>
                                                    <DeleteIcon />
                                                </IconButton>
                                            </TableCell>
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </TableContainer>

                    <TablePagination
                        component="div"
                        count={data?.total || 0}
                        page={page}
                        onPageChange={(_, newPage) => setPage(newPage)}
                        rowsPerPage={rowsPerPage}
                        onRowsPerPageChange={(e) => {
                            setRowsPerPage(parseInt(e.target.value, 10));
                            setPage(0);
                        }}
                    />
                </CardContent>
            </Card>
            {/* Delete Confirmation Dialog */}
            <Dialog open={!!deleteTarget} onClose={() => setDeleteTarget(null)}>
                <DialogTitle>Delete Member</DialogTitle>
                <DialogContent>
                    <DialogContentText>
                        Are you sure you want to delete this member? This action cannot be undone.
                    </DialogContentText>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setDeleteTarget(null)}>Cancel</Button>
                    <Button
                        onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
                        color="error"
                        variant="contained"
                        disabled={deleteMutation.isPending}
                    >
                        {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
